"""
ChainSniper - Simple blockchain event monitoring.

A builder-pattern API for watching blockchain events with automatic decoding.
Accepts a plain RPC URL (str) or an RPCPool for fault-tolerant multi-endpoint
setups.

Performance improvements over the original:
  - Smart block_detail: defaults to HEADER; auto-upgrades to FULL_BLOCK only
    when on_block or on_transaction callbacks are registered.
  - Callbacks are wrapped once at registration time, not re-wrapped on every
    pool failover, eliminating redundant closure allocation.
  - chain_id is resolved before _create_listener() so POA middleware is always
    injected correctly on the first attempt.
  - _create_listener() deduplicates the block_detail enum resolution.
  - _fetch_chain_id is skipped entirely when RPCPool already carries
    expected_chain_id, avoiding an extra HTTP round-trip on startup.
  - Wrapped callbacks are stored separately from raw callbacks so
        re-registering
    on pool rotation reuses the already-wrapped closures instead of building
        new ones.
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
from chain_sniper.filters import Filter
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

    def __init__(
        self, rpc: Union[str, "RPCPool"], chain_id: int | None = None
    ) -> None:
        """
        Args:
            rpc: A plain WebSocket / HTTP RPC URL  *or*  an RPCPool instance.
                 When an RPCPool is supplied the pool picks the fastest healthy
                 endpoint automatically and rotates on failures.
            chain_id: Optional chain ID. If provided, will be used to determine
                      if POA middleware is needed.
        """
        if isinstance(rpc, str):
            self._rpc_pool: Optional["RPCPool"] = None
            self.rpc_url: str = rpc
        else:
            self._rpc_pool = rpc
            self.rpc_url = rpc.get_rpc()

        self._listener: Optional[Union[WebSocketListener, HttpListener]] = None
        self._filters: List[Any] = []

        # Raw (unwrapped) callbacks — source of truth for pool rotation.
        self._event_callbacks: List[EventCallback] = []
        self._block_callbacks: List[BlockCallback] = []
        self._error_callbacks: List[ErrorCallback] = []
        self._tx_callbacks: List[TxCallback] = []
        self._reorg_callbacks: List[ReorgCallback] = []

        # Wrapped callbacks built once in start() and reused on failover.
        # Keys match the listener event names: "log", "block", "error",
        # "transaction", "reorg".
        self._wrapped: dict[str, list[Callable]] = {
            "log": [],
            "block": [],
            "error": [],
            "transaction": [],
            "reorg": [],
        }

        # FIX: default to HEADER — the cheapest mode.
        # Auto-upgraded to full_block in on_block / on_transaction if needed.
        self._block_detail: str = "header"
        self._poll_interval: float = 2.0
        self._chain_id: int | None = chain_id
        self._logger = logging.getLogger("ChainSniper")

        # Track whether _wrapped has been built yet.
        self._callbacks_wrapped: bool = False

    # Pool-aware RPC helpers
    def _get_rpc_url(self) -> str:
        """Return the current best RPC URL, re-querying the pool each time."""
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
        """
        Resolve chain_id exactly once before the listener is created.

        Priority:
          1. Already set by the caller — do nothing.
          2. RPCPool carries expected_chain_id — use it (no HTTP call).
          3. Fetch from the RPC endpoint (one HTTP call, then cached).
        """
        if self._chain_id is not None:
            return

        if (
            self._rpc_pool is not None
            and self._rpc_pool.expected_chain_id is not None
        ):
            self._chain_id = self._rpc_pool.expected_chain_id
            return

        self._chain_id = await self._fetch_chain_id(self.rpc_url)

    async def _fetch_chain_id(self, url: str) -> int:
        """Fetch chain ID from the RPC endpoint (one-time startup probe)."""
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

    # Builder API
    def event(
        self,
        contract: Optional[Union[str, List[str]]] = None,
        abi: Optional[Union[List[dict], str]] = None,
        name: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> Callable[[EventCallback], EventCallback]:
        """
        Decorator for registering event (log) handlers.

        Args:
            contract: Contract address(es) to watch
            abi: Contract ABI (list or JSON string)
            name: Event name to filter (e.g., "Transfer")
            topics: Raw topic hashes (alternative to abi+name)
        """
        def decorator(callback: EventCallback) -> EventCallback:
            # Defer listener creation to start() so chain_id is resolved first.
            self._event_callbacks.append(callback)
            self._register_log_filter(
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
        """
        Watch for specific contract events (fluent API).

        Args:
            abi: Contract ABI (list or JSON string)
            address: Contract address(es) to watch
            event: Event name to filter (e.g., "Transfer")
            topics: Raw topic hashes (alternative to abi+event)
        """
        self._register_log_filter(
            abi=abi, address=address, name=event, topics=topics
        )
        return self

    def filter(
        self, filter_obj: Optional[Any] = None, **rules
    ) -> "ChainSniper":
        """Add filtering logic."""
        if filter_obj is None and rules:
            filter_obj = Filter()
            for key, value in rules.items():
                if key == "tx":
                    for rule in value:
                        filter_obj.add_tx_rule(rule)
                elif key == "log":
                    for rule in value:
                        filter_obj.add_log_rule(rule)

        if filter_obj:
            self._filters.append(filter_obj)

        return self

    def on_event(self, callback: EventCallback) -> "ChainSniper":
        """Register event callback for log events."""
        self._event_callbacks.append(callback)
        return self

    def on_block(self, callback: BlockCallback) -> "ChainSniper":
        """
        Register block callback.
        Automatically upgrades block_detail to FULL_BLOCK so the callback
        receives complete block bodies with transactions.
        """
        self._block_callbacks.append(callback)
        # A block callback implies the caller wants transaction data.
        self._block_detail = "full_block"
        return self

    def on_error(self, callback: ErrorCallback) -> "ChainSniper":
        """Register error callback."""
        self._error_callbacks.append(callback)
        return self

    def on_transaction(self, callback: TxCallback) -> "ChainSniper":
        """
        Register a callback for individual transaction events.
        Automatically upgrades block_detail to FULL_BLOCK.
        """
        self._tx_callbacks.append(callback)
        self._block_detail = "full_block"
        return self

    def on_reorg(self, callback: ReorgCallback) -> "ChainSniper":
        """Register a callback for reorg events (no filter wrapping)."""
        self._reorg_callbacks.append(callback)
        return self

    def block_detail(self, detail: str) -> "ChainSniper":
        """
        Explicitly set block detail level: 'header' or 'full_block'.
        Use this to override the smart default when you need manual control.
        """
        self._block_detail = detail
        return self

    def poll_interval(self, seconds: float) -> "ChainSniper":
        """Set polling interval for HTTP listener."""
        self._poll_interval = seconds
        return self

    # Internal: log filter registration (deferred — no listener needed)
    # Pending log filters accumulated before start() creates the listener.
    # Each entry: {"abi": ..., "address": ..., "name": ..., "topics": ...}
    def _register_log_filter(
        self,
        *,
        abi=None,
        address=None,
        name=None,
        topics=None,
    ) -> None:
        """
        Accumulate a log filter specification.  The filter is applied to the
        listener inside _create_listener() once chain_id is known.
        """
        if not hasattr(self, "_pending_log_filters"):
            self._pending_log_filters: list[dict] = []

        if topics is None and (abi is None or name is None):
            raise ValueError(
                "Either provide topics or both abi and name/event"
            )

        self._pending_log_filters.append(
            {"abi": abi, "address": address, "name": name, "topics": topics}
        )

    def _apply_pending_log_filters(self) -> None:
        """Push accumulated log filter specs onto the live listener."""
        for spec in getattr(self, "_pending_log_filters", []):
            if spec["topics"] is not None:
                self._listener.add_abi_log_filter(
                    abi=spec["abi"],
                    address=spec["address"],
                    topics=spec["topics"],
                )
            else:
                self._listener.add_abi_log_filter(
                    abi=spec["abi"],
                    address=spec["address"],
                    event_name=spec["name"],
                )

    # Internal: callback wrapping
    def _build_wrapped_callbacks(self) -> None:
        """
        Wrap all raw callbacks with filter logic exactly once and store them
        in self._wrapped.  Subsequent calls (e.g. after pool rotation) reuse
        the same wrapped closures — no new closures are allocated.
        """
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
        """Register all pre-wrapped callbacks onto the current listener."""
        for event, callbacks in self._wrapped.items():
            for cb in callbacks:
                self._listener.on(event, cb)

    def _wrap_event_callback(self, callback: EventCallback) -> EventCallback:
        """Wrap an event callback to apply filters before execution."""
        if not self._filters:
            return callback

        # Capture filters at wrap time — list is stable after start().
        filters = list(self._filters)

        async def wrapped_callback(event: dict) -> None:
            for filter_obj in filters:
                try:
                    if filter_obj.match_log(event):
                        await callback(event)
                        return
                except Exception:
                    pass

        return wrapped_callback

    def _wrap_block_callback(self, callback: BlockCallback) -> BlockCallback:
        """Wrap a block callback to apply filters to transactions."""
        if not self._filters:
            return callback

        filters = list(self._filters)

        async def wrapped_callback(block: dict) -> None:
            if not block:
                return

            transactions = block.get("transactions", [])
            if transactions and isinstance(transactions[0], AttributeDict):
                filtered_txs = []
                for tx in transactions:
                    for filter_obj in filters:
                        try:
                            if filter_obj.match(tx):
                                filtered_txs.append(tx)
                                break
                        except Exception:
                            pass

                if filtered_txs:
                    filtered_block = {**block, "transactions": filtered_txs}
                    await callback(filtered_block)
            else:
                await callback(block)

        return wrapped_callback

    def _wrap_tx_callback(self, callback: TxCallback) -> TxCallback:
        """Wrap a tx callback to apply Filter.match before invoking it."""
        if not self._filters:
            return callback

        filters = list(self._filters)

        async def wrapped_callback(tx: dict) -> None:
            for filter_obj in filters:
                try:
                    if filter_obj.match(tx):
                        await callback(tx)
                        return
                except Exception:
                    pass

        return wrapped_callback

    # Lifecycle
    async def start(self) -> None:
        """Start the listener and begin monitoring."""
        # 1. Resolve chain_id ONCE before any listener is created.
        #    This guarantees POA middleware is injected correctly on the
        #    very first connection attempt.
        await self._resolve_chain_id()

        # 2. Create listener now that chain_id is known.
        if not self._listener:
            self._create_listener()

        # 3. Apply deferred log filters to the freshly created listener.
        self._apply_pending_log_filters()

        # 4. Build wrapped callbacks exactly once.
        self._build_wrapped_callbacks()

        # 5. Register them on the listener.
        self._register_wrapped_callbacks()

        await self._run_with_pool_rotation()

    def stop(self) -> None:
        """Stop the listener.
            Also stops the pool's health monitor if one is attached."""
        if self._listener:
            self._listener.stop()
        if self._rpc_pool is not None:
            self._rpc_pool.stop()

    # Internal: listener creation
    def _create_listener(self) -> None:
        """
        Create the appropriate listener for the current rpc_url.

        chain_id must already be resolved before calling this so that POA
        middleware can be injected on the first connection.
        """
        url = self._get_rpc_url()

        # Resolve enum once — used by both branches below.
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
            )
        else:
            self._listener = HttpListener(
                url,
                block_detail=block_detail_enum,
                poll_interval=self._poll_interval,
                chain_id=self._chain_id,
            )

    # Internal: pool rotation
    async def _run_with_pool_rotation(self) -> None:
        """
        Run the listener.  When a pool is present, catch transport errors,
        mark the failed endpoint, rotate to the next healthy one, recreate
        the listener, and resume — transparently to the caller.

        Callbacks are NOT re-wrapped on rotation; the pre-built closures in
        self._wrapped are reused directly.
        """
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

                # Rotate to new endpoint.
                self.rpc_url = next_url
                self._listener = None

                # chain_id is already known — no need to re-fetch.
                self._create_listener()

                # Apply log filters to the fresh listener.
                self._apply_pending_log_filters()

                # Reuse the already-wrapped callbacks (no new closures).
                self._register_wrapped_callbacks()
