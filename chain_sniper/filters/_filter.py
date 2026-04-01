"""
Versatile filter that combines dynamic rules and static target matching.
"""

import logging
import json
import threading
from uuid import uuid4
from typing import Any, Dict, List, Optional
from chain_sniper.filters.base import BaseFilter
from chain_sniper.parser.rule_parser import RuleMatcher
from chain_sniper.parser.log_decoder import LogDecoder


class Filter(BaseFilter):
    """
    A versatile filter that combines dynamic rule matching
    with static target matching.

    Rules are stored as {"id": str, "rule": dict} entries.
    Each add_tx_rule / add_log_rule call returns the assigned rule_id
    so callers can remove the rule later.

    Thread-safe: a threading.Lock guards all mutations and is released
    before calling RuleMatcher (which may be slow).
    """

    def __init__(
        self,
        logger: logging.Logger = logging.getLogger(__name__)
    ):
        # Dynamic filter properties — entries are {"id": str, "rule": dict}
        self.tx_rules: List[Dict[str, Any]] = []
        self.log_rules: List[Dict[str, Any]] = []

        # Maps rule_id -> "tx" | "log" for O(1) type lookup
        self._rule_index: Dict[str, str] = {}

        # Lock guarding all mutations to tx_rules, log_rules, _rule_index
        self._lock = threading.Lock()

        self.rule_matcher = RuleMatcher(logger=logger)

        # Log decoding properties
        self._log_decoder = LogDecoder()
        self._abi_map: Dict[str, List[Dict[str, Any]]] = {}

        self.logger = logger

    # Rule addition

    def add_tx_rule(self, rule: Dict[str, Any]) -> str:
        """
        Add a transaction rule using MongoDB-style operators.

        Returns:
            rule_id: unique string ID assigned to this rule.
        """
        rule_id = str(uuid4())
        entry = {"id": rule_id, "rule": rule}
        with self._lock:
            self.tx_rules.append(entry)
            self._rule_index[rule_id] = "tx"
        self.logger.info(f"Added TX rule id={rule_id}: {rule}")
        return rule_id

    def add_log_rule(self, rule: Dict[str, Any]) -> str:
        """
        Add a log rule using MongoDB-style operators.

        Returns:
            rule_id: unique string ID assigned to this rule.
        """
        rule_id = str(uuid4())
        entry = {"id": rule_id, "rule": rule}
        with self._lock:
            self.log_rules.append(entry)
            self._rule_index[rule_id] = "log"
        self.logger.info(f"Added log rule id={rule_id}: {rule}")
        return rule_id

    # Rule removal

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a rule (TX or log) by its ID.

        Returns:
            True if the rule was found and removed, False otherwise.
        """
        with self._lock:
            rule_type = self._rule_index.get(rule_id)
            if rule_type is None:
                self.logger.warning(f"remove_rule: unknown rule_id={rule_id}")
                return False
            target_list = (
                self.tx_rules if rule_type == "tx" else self.log_rules
            )
            for i, entry in enumerate(target_list):
                if entry["id"] == rule_id:
                    del target_list[i]
                    del self._rule_index[rule_id]
                    self.logger.info(f"Removed {rule_type} rule id={rule_id}")
                    return True
            # Index pointed to a list that no longer contains the entry
            del self._rule_index[rule_id]
            self.logger.warning(
                f"remove_rule: rule_id={rule_id} in index but not in list"
            )
            return False

    def remove_tx_rule(self, rule_id: str) -> bool:
        """Convenience wrapper — remove a TX rule by ID."""
        return self.remove_rule(rule_id)

    def remove_log_rule(self, rule_id: str) -> bool:
        """Convenience wrapper — remove a log rule by ID."""
        return self.remove_rule(rule_id)

    def clear_tx_rules(self) -> None:
        """Remove all TX rules."""
        with self._lock:
            tx_ids = [e["id"] for e in self.tx_rules]
            self.tx_rules.clear()
            for rid in tx_ids:
                self._rule_index.pop(rid, None)
        self.logger.info("Cleared all TX rules")

    def clear_log_rules(self) -> None:
        """Remove all log rules."""
        with self._lock:
            log_ids = [e["id"] for e in self.log_rules]
            self.log_rules.clear()
            for rid in log_ids:
                self._rule_index.pop(rid, None)
        self.logger.info("Cleared all log rules")

    def clear_rules(self) -> None:
        """Clear all dynamic rules (both TX and log)."""
        with self._lock:
            self.tx_rules.clear()
            self.log_rules.clear()
            self._rule_index.clear()
        self.logger.info("Cleared all dynamic rules")

    # Matching

    def match(self, tx: Dict[str, Any]) -> bool:
        """
        Check if transaction matches any TX rule.

        Takes a snapshot of the rule list under the lock, then releases
        the lock before calling RuleMatcher.
        """
        with self._lock:
            snapshot = list(self.tx_rules)

        for entry in snapshot:
            try:
                if self.rule_matcher.match_rule(tx, entry["rule"]):
                    return True
            except (ValueError, KeyError) as e:
                self.logger.error(f"TX rule error id={entry['id']}: {e}")

        return False

    def match_log(self, log: Dict[str, Any]) -> bool:
        """
        Check if log matches any log rule.

        Takes a snapshot of the rule list under the lock, then releases
        the lock before calling RuleMatcher.
        """
        with self._lock:
            snapshot = list(self.log_rules)

        if not snapshot:
            return False

        decoded_log = self._decode_log(log)

        for entry in snapshot:
            try:
                if self.rule_matcher.match_rule(decoded_log, entry["rule"]):
                    return True
            except (ValueError, KeyError) as e:
                self.logger.error(f"Log rule error id={entry['id']}: {e}")

        return False

    # ABI registration

    def add_abi(
        self, abi: List[Dict[str, Any]] | str, address: Optional[str] = None
    ):
        """Register an ABI for log decoding."""
        if isinstance(abi, str):
            abi = json.loads(abi)
        key = address.lower() if address else "*"
        self._abi_map[key] = abi
        self.logger.info(f"Registered ABI for address: {address or 'all'}")

    def _decode_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        address = log.get("address")
        address_lower = address.lower() if address else None
        topics = log.get("topics", [])

        if topics:
            topic = topics[0]
            if hasattr(topic, 'hex'):
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

    # Config / introspection

    def get_config(self) -> Dict[str, Any]:
        """Return the current filter configuration."""
        with self._lock:
            tx_count = len(self.tx_rules)
            log_count = len(self.log_rules)
            tx_ids = [e["id"] for e in self.tx_rules]
            log_ids = [e["id"] for e in self.log_rules]
        return {
            "tx_rules_count": tx_count,
            "log_rules_count": log_count,
            "has_dynamic_rules": bool(tx_count or log_count),
            "registered_abis": len(self._abi_map),
            "tx_rule_ids": tx_ids,
            "log_rule_ids": log_ids,
        }
