"""
Log subscription manager with optional post-filtering.

Unlike transactions (where we receive all and filter locally), logs are
pre-filtered at the node level — you tell the node *exactly* which logs
you want by specifying address + topics.  This module manages those
subscription specs and integrates with the WebSocket listener via
``eth_subscribe("logs", params)``.

When a subscription is added at runtime and a listener is bound, the
listener is notified so it can open a live subscription on the node.
"""

import asyncio
import json
import logging
import threading
from uuid import uuid4
from typing import Any, Callable, Dict, List, Optional

from chain_sniper.parser.rule_parser import RuleMatcher
from chain_sniper.parser.log_decoder import LogDecoder
from chain_sniper.utils.abi_filter import ABIFilterRegistry


class LogFilter:
    """
    Manages log subscriptions and optional post-filtering.

    **Subscriptions** define what logs are requested from the node
    (address + topics).  When connected to a listener, adding / removing
    subscriptions triggers live subscribe / unsubscribe on the node.

    **Post-filter rules** (optional) can be added for additional
    filtering on *decoded* log data — for the rare cases where node-level
    filtering isn't granular enough.
    """

    def __init__(
        self,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        # Subscription specs: what to request from the node
        self._subscriptions: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        # ABI filter registry for decoding and topic generation
        self._abi_filter = ABIFilterRegistry()

        # Optional post-filter rules
        self._rules: List[Dict[str, Any]] = []
        self._rule_matcher = RuleMatcher(logger=logger)

        # Log decoding (manual ABI registration)
        self._log_decoder = LogDecoder()
        self._abi_map: Dict[str, List[Dict[str, Any]]] = {}

        # Listener callbacks for dynamic subscribe / unsubscribe.
        # Set via ``bind_listener`` when the listener starts;
        # cleared via ``unbind_listener`` on disconnect / cleanup.
        self._on_subscribe: Optional[Callable[..., Any]] = None
        self._on_unsubscribe: Optional[Callable[..., Any]] = None

        self.logger = logger

    #  Listener integration 

    def bind_listener(
        self,
        on_subscribe: Callable[..., Any],
        on_unsubscribe: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Bind listener callbacks for dynamic subscription management.

        Called by the listener at startup so that future
        ``subscribe()`` / ``unsubscribe()`` calls can push changes to
        the node in real-time.

        Args:
            on_subscribe:   Called with the subscription spec dict when a
                            new subscription is added.  May be sync or
                            async (coroutine).
            on_unsubscribe: Called with the subscription spec dict when a
                            subscription is removed.  May be sync or
                            async.
        """
        self._on_subscribe = on_subscribe
        self._on_unsubscribe = on_unsubscribe

    def unbind_listener(self) -> None:
        """Remove listener callbacks (e.g. on disconnect / cleanup)."""
        self._on_subscribe = None
        self._on_unsubscribe = None

    #  Subscription management 

    def subscribe(
        self,
        address: str | list[str] | None = None,
        topics: list[str | list[str] | None] | None = None,
        abi: list | str | None = None,
        event_name: str | None = None,
    ) -> str:
        """
        Add a log subscription spec.

        You can provide either:
          - ``address`` + ``topics`` (raw values)
          - ``abi`` + ``event_name`` (topics auto-generated from the ABI)
          - ``abi`` + ``address`` + ``event_name``

        When a listener is bound, this triggers a live subscription on
        the node (``eth_subscribe`` for WS).

        Returns:
            sub_id - unique ID for this subscription.
        """
        # Generate topics from ABI when not provided explicitly
        if topics is None:
            if abi is None or event_name is None:
                raise ValueError(
                    "Provide either topics or both abi and event_name"
                )
            generated_topics = self._abi_filter.register_abi_filter(
                abi=abi, address=address, event_name=event_name,
            )
            topics = generated_topics
        elif abi is not None:
            # Register ABI for decoding even when topics are explicit
            self._abi_filter.register_abi_filter(
                abi=abi, address=address, topics=topics,
            )

        sub_id = str(uuid4())
        spec: Dict[str, Any] = {
            "id": sub_id,
            "address": address,
            "topics": topics,
            "node_sub_id": None,   # populated by the listener
            "filter_id": None,     # populated by HTTP listener
        }

        with self._lock:
            self._subscriptions.append(spec)

        self.logger.info(
            "Added log subscription id=%s address=%s topics=%s",
            sub_id, address, topics,
        )

        # Notify listener if bound
        self._notify_subscribe(spec)
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """
        Remove a log subscription by ID.

        If a listener is bound, triggers unsubscribe on the node.

        Returns:
            True if found and removed.
        """
        with self._lock:
            for i, spec in enumerate(self._subscriptions):
                if spec["id"] == sub_id:
                    removed_spec = self._subscriptions.pop(i)
                    break
            else:
                self.logger.warning(
                    "unsubscribe: unknown sub_id=%s", sub_id,
                )
                return False

        self.logger.info("Removed log subscription id=%s", sub_id)
        self._notify_unsubscribe(removed_spec)
        return True

    def clear_subscriptions(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            specs = list(self._subscriptions)
            self._subscriptions.clear()

        for spec in specs:
            self._notify_unsubscribe(spec)

        self.logger.info("Cleared all log subscriptions")

    def get_subscriptions(self) -> List[Dict[str, Any]]:
        """Return a snapshot of all active subscription specs."""
        with self._lock:
            return list(self._subscriptions)

    #  Optional post-filtering 

    def add_rule(self, rule: Dict[str, Any]) -> str:
        """
        Add a post-filter rule for decoded logs.

        Use this when you need additional filtering beyond what
        address + topics provide at the node level.

        Returns:
            rule_id - unique string ID assigned to this rule.
        """
        rule_id = str(uuid4())
        entry = {"id": rule_id, "rule": rule}
        with self._lock:
            self._rules.append(entry)
        self.logger.info(
            "Added log post-filter rule id=%s: %s", rule_id, rule,
        )
        return rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a post-filter rule by ID."""
        with self._lock:
            for i, entry in enumerate(self._rules):
                if entry["id"] == rule_id:
                    del self._rules[i]
                    self.logger.info(
                        "Removed log post-filter rule id=%s", rule_id,
                    )
                    return True
        self.logger.warning("remove_rule: unknown rule_id=%s", rule_id)
        return False

    def clear_rules(self) -> None:
        """Remove all post-filter rules."""
        with self._lock:
            self._rules.clear()
        self.logger.info("Cleared all log post-filter rules")

    def match(self, log: Dict[str, Any]) -> bool:
        """
        Check whether a decoded log matches any post-filter rule.

        If **no** rules are set, returns ``True`` (all logs pass through).
        """
        with self._lock:
            snapshot = list(self._rules)

        if not snapshot:
            return True  # no post-filtering — accept all

        decoded = self._decode_log(log)

        for entry in snapshot:
            try:
                if self._rule_matcher.match_rule(decoded, entry["rule"]):
                    return True
            except (ValueError, KeyError) as exc:
                self.logger.error(
                    "Log rule error id=%s: %s", entry["id"], exc,
                )

        return False

    #  ABI / Decoding 

    def add_abi(
        self, abi: list | str, address: Optional[str] = None,
    ) -> None:
        """Register an ABI for log decoding."""
        if isinstance(abi, str):
            abi = json.loads(abi)
        key = address.lower() if address else "*"
        self._abi_map[key] = abi
        self.logger.info(
            "Registered ABI for address: %s", address or "all",
        )

    def decode_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decode a log using registered ABIs.

        Tries the ABI filter registry first (populated by ``subscribe``
        calls), then falls back to manually registered ABIs.
        """
        decoded = self._abi_filter.decode_log(log)
        if decoded is not log:
            return decoded
        return self._decode_log(log)

    def _decode_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        address = log.get("address")
        address_lower = address.lower() if address else None
        topics = log.get("topics", [])

        if topics:
            topic = topics[0]
            if hasattr(topic, "hex"):
                topic = topic.hex()
            elif isinstance(topic, bytes):
                topic = topic.hex()
            abi = self._abi_map.get(address_lower)
            if abi:
                return self._log_decoder.decode_log(log, abi)
            abi = self._abi_map.get("*")
            if abi:
                return self._log_decoder.decode_log(log, abi)

        return log

    #  Introspection 

    @property
    def has_subscriptions(self) -> bool:
        with self._lock:
            return bool(self._subscriptions)

    @property
    def has_rules(self) -> bool:
        with self._lock:
            return bool(self._rules)

    def get_config(self) -> Dict[str, Any]:
        """Return the current filter configuration."""
        with self._lock:
            sub_count = len(self._subscriptions)
            rule_count = len(self._rules)
            sub_ids = [s["id"] for s in self._subscriptions]
            rule_ids = [e["id"] for e in self._rules]
        return {
            "subscriptions_count": sub_count,
            "post_filter_rules_count": rule_count,
            "subscription_ids": sub_ids,
            "rule_ids": rule_ids,
            "registered_abis": len(self._abi_map),
        }

    #  Private helpers 

    def _notify_subscribe(self, spec: Dict[str, Any]) -> None:
        """Notify the bound listener of a new subscription."""
        if self._on_subscribe is None:
            return
        try:
            result = self._on_subscribe(spec)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    pass  # no event loop — listener will pick up on start
        except Exception as exc:
            self.logger.error("on_subscribe callback error: %s", exc)

    def _notify_unsubscribe(self, spec: Dict[str, Any]) -> None:
        """Notify the bound listener to tear down a subscription."""
        if self._on_unsubscribe is None:
            return
        try:
            result = self._on_unsubscribe(spec)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    pass
        except Exception as exc:
            self.logger.error("on_unsubscribe callback error: %s", exc)
