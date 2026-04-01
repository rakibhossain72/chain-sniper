"""
ChainSniper - Simple blockchain event monitoring.

A builder-pattern API for watching blockchain events with automatic decoding.
Accepts a plain RPC URL (str) or an RPCPool
    for fault-tolerant multi-endpoint setups.
"""

import time
import asyncio
import aiohttp
from typing import Any, Optional, Union, List, Callable
from web3.datastructures import AttributeDict
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.poll_listener import HttpListener
from chain_sniper.listener.common import BlockDetail
from chain_sniper.filters import Filter
from chain_sniper.types import EventCallback, BlockCallback, ErrorCallback, TxCallback, ReorgCallback
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
        # Resolve the URL to use for the listener.
        if isinstance(rpc, str):
            self._rpc_pool: Optional["RPCPool"] = None
            self.rpc_url: str = rpc
        else:
            # RPCPool passed — pull the best URL now; we re-ask on reconnect.
            self._rpc_pool = rpc
            self.rpc_url = rpc.get_rpc()

        self._listener: Optional[Union[WebSocketListener, HttpListener]] = None
        self._filters: List[Any] = []
        self._event_callbacks: List[EventCallback] = []
        self._block_callbacks: List[BlockCallback] = []
        self._error_callbacks: List[ErrorCallback] = []
        self._tx_callbacks: List[TxCallback] = []
        self._reorg_callbacks: List[ReorgCallback] = []
        self._block_detail = "full_block"
        self._poll_interval = 2.0
        self._chain_id = chain_id

    # ------------------------------------------------------------------ #
    # Pool-aware RPC helpers                                               #
    # ------------------------------------------------------------------ #

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

    async def _fetch_chain_id(self, url: str) -> int:
        """Fetch chain ID from the RPC endpoint."""
        # Convert WebSocket URL to HTTP for probing
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

    # ------------------------------------------------------------------ #
    # Builder API — unchanged from original                                #
    # ------------------------------------------------------------------ #

    def event(
        self,
        contract: Optional[Union[str, List[str]]] = None,
        abi: Optional[Union[List[dict], str]] = None,
        name: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> Callable[[EventCallback], EventCallback]:
        """
        Decorator for registering event handlers.

        Args:
            contract: Contract address(es) to watch
            abi: Contract ABI (list or JSON string)
            name: Event name to filter (e.g., "Transfer")
            topics: Raw topic hashes (alternative to abi+name)
        """
        def decorator(callback: EventCallback) -> EventCallback:
            if not self._listener:
                self._create_listener()

            if topics:
                # Pass ABI for decoding even when topics are provided
                self._listener.add_abi_log_filter(
                        abi=abi, address=contract, topics=topics
                    )
            elif abi and name:
                self._listener.add_abi_log_filter(
                        abi=abi, address=contract, event_name=name
                    )
            else:
                raise ValueError("Either provide topics or both abi and name")

            self._event_callbacks.append(callback)
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
        Watch for specific contract events.

        Args:
            abi: Contract ABI (list or JSON string)
            address: Contract address(es) to watch
            event: Event name to filter (e.g., "Transfer")
            topics: Raw topic hashes (alternative to abi+event)
        """
        if not self._listener:
            self._create_listener()

        if topics:
            # Pass ABI for decoding even when topics are provided
            self._listener.add_abi_log_filter(
                abi=abi, address=address, topics=topics
            )
        elif abi and event:
            self._listener.add_abi_log_filter(
                    abi=abi, address=address, event_name=event
                )
        else:
            raise ValueError("Either provide topics or both abi and event")

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
        """Register block callback."""
        self._block_callbacks.append(callback)
        return self

    def on_error(self, callback: ErrorCallback) -> "ChainSniper":
        """Register error callback."""
        self._error_callbacks.append(callback)
        return self

    def on_transaction(self, callback: TxCallback) -> "ChainSniper":
        """Register a callback for individual transaction events."""
        self._tx_callbacks.append(callback)
        return self

    def on_reorg(self, callback: ReorgCallback) -> "ChainSniper":
        """Register a callback for reorg events (no filter wrapping — always significant)."""
        self._reorg_callbacks.append(callback)
        return self

    def block_detail(self, detail: str) -> "ChainSniper":
        """Set block detail level: 'header' or 'full_block'."""
        self._block_detail = detail
        return self

    def poll_interval(self, seconds: float) -> "ChainSniper":
        """Set polling interval for HTTP listener."""
        self._poll_interval = seconds
        return self

    def _wrap_event_callback(self, callback: EventCallback) -> EventCallback:
        """Wrap an event callback to apply filters before execution."""
        if not self._filters:
            return callback

        async def wrapped_callback(event: dict) -> None:
            # Apply all filters - event must match at least one
            for filter_obj in self._filters:
                try:
                    if filter_obj.match_log(event):
                        await callback(event)
                        return
                except Exception:
                    # Log filter error but don't crash
                    pass

        return wrapped_callback

    def _wrap_block_callback(self, callback: BlockCallback) -> BlockCallback:
        """Wrap a block callback to apply filters to transactions."""
        if not self._filters:
            return callback

        async def wrapped_callback(block: dict) -> None:
            # If block has transactions, filter them
            if not block:
                return

            transactions = block.get("transactions", [])
            if transactions and isinstance(transactions[0], AttributeDict):
                # Filter transactions before calling callback
                filtered_txs = []
                for tx in transactions:
                    for filter_obj in self._filters:
                        try:
                            if filter_obj.match(tx):
                                filtered_txs.append(tx)
                                break
                        except Exception:
                            pass

                # Only call callback if there are matching transactions
                if filtered_txs:
                    # Create a copy of block with filtered transactions
                    filtered_block = {**block, "transactions": filtered_txs}
                    await callback(filtered_block)
            else:
                # No transactions or header-only mode, call callback as-is
                await callback(block)

        return wrapped_callback

    def _wrap_tx_callback(self, callback: TxCallback) -> TxCallback:
        """Wrap a tx callback to apply Filter.match before invoking it."""
        if not self._filters:
            return callback

        async def wrapped_callback(tx: dict) -> None:
            for filter_obj in self._filters:
                try:
                    if filter_obj.match(tx):
                        await callback(tx)
                        return
                except Exception:
                    pass

        return wrapped_callback

    async def start(self) -> None:
        """Start the listener and begin monitoring."""
        # Fetch chain_id if not provided
        if self._chain_id is None:
            if self._rpc_pool is not None:
                # Use expected_chain_id from the pool
                self._chain_id = self._rpc_pool.expected_chain_id
            else:
                # Fetch chain_id from the RPC endpoint
                self._chain_id = await self._fetch_chain_id(self.rpc_url)

        if not self._listener:
            self._create_listener()

        # Wrap callbacks with filter logic if filters are present
        for callback in self._event_callbacks:
            wrapped_callback = self._wrap_event_callback(callback)
            self._listener.on("log", wrapped_callback)
        for callback in self._block_callbacks:
            wrapped_callback = self._wrap_block_callback(callback)
            self._listener.on("block", wrapped_callback)
        for callback in self._error_callbacks:
            self._listener.on("error", callback)
        for callback in self._tx_callbacks:
            wrapped_callback = self._wrap_tx_callback(callback)
            self._listener.on("transaction", wrapped_callback)
        for callback in self._reorg_callbacks:
            self._listener.on("reorg", callback)

        await self._run_with_pool_rotation()
    def stop(self) -> None:
        """Stop the listener.
        Also stops the pool's health monitor if one is attached.
        """
        if self._listener:
            self._listener.stop()
        if self._rpc_pool is not None:
            self._rpc_pool.stop()

    async def _run_with_pool_rotation(self) -> None:
        """
        Run the listener.  When a pool is present, catch transport errors,
        mark the failed endpoint, rotate to the next healthy one, recreate
        the listener, and resume — transparently to the caller.
        """
        if self._rpc_pool is None:
            # No pool — plain run, same as original behaviour.
            await self._listener.start()
            return

        while True:
            current_url = self.rpc_url
            t0 = time.monotonic()
            try:
                await self._listener.start()
                # Listener exited cleanly — record success and stop.
                elapsed = (time.monotonic() - t0) * 1000
                self._on_rpc_success(current_url, elapsed)
                return
            except Exception as exc:
                self._on_rpc_failure(current_url)
                # Propagate to registered error callbacks, then rotate.
                for cb in self._error_callbacks:
                    try:
                        asyncio.get_event_loop().call_soon(
                            lambda exc=exc: asyncio.ensure_future(cb(exc))
                        )
                    except Exception:
                        pass

                try:
                    next_url = self._get_rpc_url()
                except RuntimeError:
                    # All endpoints exhausted — surface the original error.
                    raise exc from None

                if next_url == current_url:
                    raise exc from None  # Only one endpoint and it failed.

                # Recreate the listener on the new URL.
                self.rpc_url = next_url
                self._listener = None
                # Re-fetch chain_id if it was None initially
                if self._chain_id is None:
                    if self._rpc_pool is not None:
                        self._chain_id = (
                            self._rpc_pool.expected_chain_id
                        )
                    else:
                        self._chain_id = await self._fetch_chain_id(
                            self.rpc_url
                        )
                self._create_listener()
                # Re-register callbacks on the fresh listener.
                for callback in self._event_callbacks:
                    wrapped_callback = self._wrap_event_callback(callback)
                    self._listener.on("log", wrapped_callback)
                for callback in self._block_callbacks:
                    wrapped_callback = self._wrap_block_callback(callback)
                    self._listener.on("block", wrapped_callback)
                for callback in self._error_callbacks:
                    self._listener.on("error", callback)
                for callback in self._tx_callbacks:
                    wrapped_callback = self._wrap_tx_callback(callback)
                    self._listener.on("transaction", wrapped_callback)
                for callback in self._reorg_callbacks:
                    self._listener.on("reorg", callback)

    def _create_listener(self) -> None:
        """Create the appropriate listener for the current rpc_url."""
        url = self._get_rpc_url()

        if url.startswith("ws"):
            block_detail_enum = (
                BlockDetail.FULL_BLOCK if self._block_detail == "full_block"
                else BlockDetail.HEADER
            )
            self._listener = WebSocketListener(
                    url,
                    block_detail=block_detail_enum,
                    chain_id=self._chain_id
                )
        else:
            block_detail_enum = (
                BlockDetail.FULL_BLOCK if self._block_detail == "full_block"
                else BlockDetail.HEADER
            )
            self._listener = HttpListener(
                url,
                block_detail=block_detail_enum,
                poll_interval=self._poll_interval,
                chain_id=self._chain_id,
            )
