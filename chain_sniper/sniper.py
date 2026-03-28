"""
ChainSniper - Simple blockchain event monitoring.

A builder-pattern API for watching blockchain events with automatic decoding.
Accepts a plain RPC URL (str) or an RPCPool
    for fault-tolerant multi-endpoint setups.
"""

import time
from typing import Any, Optional, Union, List, Callable
import asyncio
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.poll_listener import HttpListener
from chain_sniper.filters.dynamic_filter import DynamicFilter
from chain_sniper.types import EventCallback, BlockCallback, ErrorCallback
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

    def __init__(self, rpc: Union[str, "RPCPool"]) -> None:
        """
        Args:
            rpc: A plain WebSocket / HTTP RPC URL  *or*  an RPCPool instance.
                 When an RPCPool is supplied the pool picks the fastest healthy
                 endpoint automatically and rotates on failures.
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
        self._block_detail = "full_block"
        self._poll_interval = 2.0

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
                self._listener.add_abi_log_filter(
                        address=contract, topics=topics
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
            self._listener.add_abi_log_filter(address=address, topics=topics)
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
            filter_obj = DynamicFilter()
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

    def block_detail(self, detail: str) -> "ChainSniper":
        """Set block detail level: 'header' or 'full_block'."""
        self._block_detail = detail
        return self

    def poll_interval(self, seconds: float) -> "ChainSniper":
        """Set polling interval for HTTP listener."""
        self._poll_interval = seconds
        return self

    async def start(self) -> None:
        """Start the listener and begin monitoring."""
        if not self._listener:
            self._create_listener()

        for callback in self._event_callbacks:
            self._listener.on("log", callback)
        for callback in self._block_callbacks:
            self._listener.on("block", callback)
        for callback in self._error_callbacks:
            self._listener.on("error", callback)

        await self._run_with_pool_rotation()

    def stop(self) -> None:
        """Stop the listener (and the pool's health monitor if one is attached)."""
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
                            lambda: asyncio.ensure_future(cb(exc))
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
                self._create_listener()
                # Re-register callbacks on the fresh listener.
                for callback in self._event_callbacks:
                    self._listener.on("log", callback)
                for callback in self._block_callbacks:
                    self._listener.on("block", callback)
                for callback in self._error_callbacks:
                    self._listener.on("error", callback)

    def _create_listener(self) -> None:
        """Create the appropriate listener for the current rpc_url."""
        url = self._get_rpc_url()

        if url.startswith("ws"):
            from chain_sniper.listener.websocket_listener import BlockDetail
            block_detail_enum = (
                BlockDetail.FULL_BLOCK if self._block_detail == "full_block"
                else BlockDetail.HEADER
            )
            self._listener = WebSocketListener(
                    url, block_detail=block_detail_enum
                )
        else:
            from chain_sniper.listener.poll_listener import BlockDetail
            block_detail_enum = (
                BlockDetail.FULL_BLOCK if self._block_detail == "full_block"
                else BlockDetail.HEADER
            )
            self._listener = HttpListener(
                url,
                block_detail=block_detail_enum,
                poll_interval=self._poll_interval,
            )
