"""
ChainSniper - Simple blockchain event monitoring.

A builder-pattern API for watching blockchain events with automatic decoding.
Accepts a plain RPC URL (str) or an RPCPool for fault-tolerant multi-endpoint
setups.

Architecture:
  - TransactionFilter  — local rule matching for txs / blocks.
  - LogFilter          — node-level log subscriptions + optional post-filter.
  - Listeners receive the split filter instances directly and handle the
    transport-specific details (eth_subscribe for WS, eth_newFilter for HTTP).
"""

import time
import asyncio
import logging
import aiohttp
from typing import Any, Optional, Union, List, Callable
from web3.datastructures import AttributeDict
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.poll_listener import HttpListener
from chain_sniper.listener.common import BlockDetail
from chain_sniper.filters import TransactionFilter, LogFilter
from chain_sniper.types import (
    EventCallback,
    BlockCallback,
    ErrorCallback,
    TxCallback,
    ReorgCallback,
)
from chain_sniper.rpc_pool import RPCPool


class ChainSniper:
    """
    Builder for creating blockchain event listeners.

    Accepts either a plain RPC URL or an RPCPool:

        # Simple — single endpoint
        sniper = ChainSniper("wss://rpc.example.com")

        # Robust — multi-endpoint pool (HTTP or WSS, mixed is fine)
        pool = await RPCPool.create(
            rpcs=["https://rpc1.example.com", "wss://rpc2.example.com"],
            expected_chain_id=56,
        )
        sniper = ChainSniper(pool)

        @sniper.event(contract="0x...", abi=erc20_abi, name="Transfer")
        async def handle_transfer(event):
            print(event["args"])

        await sniper.start()
    """

    def __init__(self, rpc: Union[str, "RPCPool"], chain_id: int | None = None) -> None:
        if isinstance(rpc, str):
            self._rpc_pool: Optional["RPCPool"] = None
            self.rpc_url: str = rpc
        else:
            self._rpc_pool = rpc
            self.rpc_url = rpc.get_rpc()

        self._listener: Optional[Union[WebSocketListener, HttpListener]] = None

        # Split filters — the only filtering mechanism.
        self._tx_filter: TransactionFilter = TransactionFilter()
        self._log_filter: LogFilter = LogFilter()

        # Raw (unwrapped) callbacks — source of truth for pool rotation.
        self._event_callbacks: List[EventCallback] = []
        self._block_callbacks: List[BlockCallback] = []
        self._error_callbacks: List[ErrorCallback] = []
        self._tx_callbacks: List[TxCallback] = []
        self._reorg_callbacks: List[ReorgCallback] = []

        # Wrapped callbacks built once in start() and reused on failover.
        self._wrapped: dict[str, list[Callable]] = {
            "log": [],
            "block": [],
            "error": [],
            "transaction": [],
            "reorg": [],
        }

        self._block_detail: str = "header"
        self._poll_interval: float = 2.0
        self._chain_id: int | None = chain_id
        self._logger = logging.getLogger("ChainSniper")

        self._callbacks_wrapped: bool = False

    #  Pool-aware RPC helpers 

    def _get_rpc_url(self) -> str:
        if self._rpc_pool is not None:
            self.rpc_url = self._rpc_pool.get_rpc()
        return self.rpc_url

    def _on_rpc_success(self, url: str, elapsed_ms: float) -> None:
        if self._rpc_pool is not None:
            self._rpc_pool.record_success(url, elapsed_ms)

    def _on_rpc_failure(self, url: str) -> None:
        if self._rpc_pool is not None:
            self._rpc_pool.mark_failed(url)

    async def _resolve_chain_id(self) -> None:
        if self._chain_id is not None:
            return
        if self._rpc_pool is not None and self._rpc_pool.expected_chain_id is not None:
            self._chain_id = self._rpc_pool.expected_chain_id
            return
        self._chain_id = await self._fetch_chain_id(self.rpc_url)

    async def _fetch_chain_id(self, url: str) -> int:
        probe_url = url
        if url.startswith("wss://"):
            probe_url = "https://" + url[6:]
        elif url.startswith("ws://"):
            probe_url = "http://" + url[5:]

        payload = {
            "jsonrpc": "2.0",
            "method": "eth_chainId",
            "params": [],
            "id": 1,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                probe_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                data = await resp.json(content_type=None)
                return int(data["result"], 16)

    #  Builder API 

    def event(
        self,
        contract: Optional[Union[str, List[str]]] = None,
        abi: Optional[Union[List[dict], str]] = None,
        name: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> Callable[[EventCallback], EventCallback]:
        """
        Decorator for registering event (log) handlers.

        Subscribes on the LogFilter so the node sends only matching logs.
        """

        def decorator(callback: EventCallback) -> EventCallback:
            self._event_callbacks.append(callback)
            self._register_log_subscription(
                abi=abi, address=contract, name=name, topics=topics
            )
            return callback

        return decorator

    def watch(
        self,
        abi: Optional[Union[List[dict], str]] = None,
        address: Optional[Union[str, List[str]]] = None,
        event: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> "ChainSniper":
        """Watch for specific contract events (fluent API)."""
        self._register_log_subscription(
            abi=abi, address=address, name=event, topics=topics
        )
        return self

    def filter(
        self,
        *,
        tx_filter: Optional[TransactionFilter] = None,
        log_filter: Optional[LogFilter] = None,
        tx: Optional[List[dict]] = None,
        log: Optional[List[dict]] = None,
    ) -> "ChainSniper":
        """
        Configure filtering.

        Args:
            tx_filter:  Replace the TransactionFilter instance.
            log_filter: Replace the LogFilter instance.
            tx:         Inline list of TX rule dicts to add.
            log:        Inline list of log post-filter rule dicts to add.
        """
        if tx_filter is not None:
            self._tx_filter = tx_filter
        if log_filter is not None:
            self._log_filter = log_filter
        for rule in (tx or []):
            self._tx_filter.add_rule(rule)
        for rule in (log or []):
            self._log_filter.add_rule(rule)
        return self

    def on_event(self, callback: EventCallback) -> "ChainSniper":
        """Register event callback for log events."""
        self._event_callbacks.append(callback)
        return self

    def on_block(self, callback: BlockCallback) -> "ChainSniper":
        """Register block callback. Auto-upgrades to FULL_BLOCK."""
        self._block_callbacks.append(callback)
        self._block_detail = "full_block"
        return self

    def on_error(self, callback: ErrorCallback) -> "ChainSniper":
        """Register error callback."""
        self._error_callbacks.append(callback)
        return self

    def on_transaction(self, callback: TxCallback) -> "ChainSniper":
        """Register transaction callback. Auto-upgrades to FULL_BLOCK."""
        self._tx_callbacks.append(callback)
        self._block_detail = "full_block"
        return self

    def on_reorg(self, callback: ReorgCallback) -> "ChainSniper":
        """Register a callback for reorg events."""
        self._reorg_callbacks.append(callback)
        return self

    def block_detail(self, detail: str) -> "ChainSniper":
        """Explicitly set block detail level: 'header' or 'full_block'."""
        self._block_detail = detail
        return self

    def poll_interval(self, seconds: float) -> "ChainSniper":
        """Set polling interval for HTTP listener."""
        self._poll_interval = seconds
        return self

    #  Internal: log subscription registration 

    def _register_log_subscription(
        self, *, abi=None, address=None, name=None, topics=None,
    ) -> None:
        if topics is None and (abi is None or name is None):
            raise ValueError("Either provide topics or both abi and name/event")

        if not hasattr(self, "_pending_log_specs"):
            self._pending_log_specs: list[dict] = []

        self._pending_log_specs.append(
            {"abi": abi, "address": address, "name": name, "topics": topics}
        )

    def _apply_pending_log_specs(self) -> None:
        """Push accumulated log specs into the LogFilter as subscriptions."""
        for spec in getattr(self, "_pending_log_specs", []):
            if spec["topics"] is not None:
                self._log_filter.subscribe(
                    address=spec["address"],
                    topics=spec["topics"],
                    abi=spec["abi"],
                )
            else:
                self._log_filter.subscribe(
                    abi=spec["abi"],
                    address=spec["address"],
                    event_name=spec["name"],
                )

    #  Internal: callback wrapping 

    def _build_wrapped_callbacks(self) -> None:
        if self._callbacks_wrapped:
            return

        self._wrapped["log"] = [
            self._wrap_event_callback(cb) for cb in self._event_callbacks
        ]
        self._wrapped["block"] = [
            self._wrap_block_callback(cb) for cb in self._block_callbacks
        ]
        self._wrapped["error"] = list(self._error_callbacks)
        self._wrapped["transaction"] = [
            self._wrap_tx_callback(cb) for cb in self._tx_callbacks
        ]
        self._wrapped["reorg"] = list(self._reorg_callbacks)

        self._callbacks_wrapped = True

    def _register_wrapped_callbacks(self) -> None:
        for event, callbacks in self._wrapped.items():
            for cb in callbacks:
                self._listener.on(event, cb)

    def _wrap_event_callback(self, callback: EventCallback) -> EventCallback:
        """Wrap event callback — post-filter is applied in the listener."""
        # LogFilter post-filtering is handled by the listener itself.
        # No extra wrapping needed.
        return callback

    def _wrap_block_callback(self, callback: BlockCallback) -> BlockCallback:
        """Wrap block callback to apply TransactionFilter to block txs."""
        tx_filter = self._tx_filter

        if not tx_filter.has_rules:
            return callback

        async def wrapped_callback(block: dict) -> None:
            if not block:
                return

            transactions = block.get("transactions", [])
            if transactions and isinstance(transactions[0], AttributeDict):
                filtered_txs = [
                    tx for tx in transactions if tx_filter.match(tx)
                ]
                if filtered_txs:
                    filtered_block = {**block, "transactions": filtered_txs}
                    await callback(filtered_block)
            else:
                await callback(block)

        return wrapped_callback

    def _wrap_tx_callback(self, callback: TxCallback) -> TxCallback:
        """Wrap tx callback to apply TransactionFilter.match."""
        tx_filter = self._tx_filter

        if not tx_filter.has_rules:
            return callback

        async def wrapped_callback(tx: dict) -> None:
            if tx_filter.match(tx):
                await callback(tx)

        return wrapped_callback

    #  Lifecycle 

    async def start(self) -> None:
        """Start the listener and begin monitoring."""
        await self._resolve_chain_id()

        # Apply pending log specs to the LogFilter.
        self._apply_pending_log_specs()

        # Create listener with split filters.
        if not self._listener:
            self._create_listener()

        # Build & register wrapped callbacks.
        self._build_wrapped_callbacks()
        self._register_wrapped_callbacks()

        await self._run_with_pool_rotation()

    def stop(self) -> None:
        """Stop the listener."""
        if self._listener:
            self._listener.stop()
        if self._rpc_pool is not None:
            self._rpc_pool.stop()

    #  Internal: listener creation 

    def _create_listener(self) -> None:
        url = self._get_rpc_url()
        block_detail_enum = (
            BlockDetail.FULL_BLOCK
            if self._block_detail == "full_block"
            else BlockDetail.HEADER
        )

        if url.startswith("ws"):
            self._listener = WebSocketListener(
                url,
                block_detail=block_detail_enum,
                chain_id=self._chain_id,
                log_filter=self._log_filter,
                transaction_filter=self._tx_filter,
            )
        else:
            self._listener = HttpListener(
                url,
                block_detail=block_detail_enum,
                poll_interval=self._poll_interval,
                chain_id=self._chain_id,
                log_filter=self._log_filter,
                transaction_filter=self._tx_filter,
            )

    #  Internal: pool rotation 

    async def _run_with_pool_rotation(self) -> None:
        if self._rpc_pool is None:
            await self._listener.start()
            return

        while True:
            current_url = self.rpc_url
            t0 = time.monotonic()
            try:
                await self._listener.start()
                elapsed = (time.monotonic() - t0) * 1000
                self._on_rpc_success(current_url, elapsed)
                return
            except Exception as exc:
                self._on_rpc_failure(current_url)

                for cb in self._wrapped["error"]:
                    try:
                        asyncio.get_event_loop().call_soon(
                            lambda exc=exc: asyncio.ensure_future(cb(exc))
                        )
                    except Exception:
                        pass

                try:
                    next_url = self._get_rpc_url()
                except RuntimeError:
                    raise exc from None

                if next_url == current_url:
                    raise exc from None

                self.rpc_url = next_url
                self._listener = None

                self._create_listener()
                self._register_wrapped_callbacks()
