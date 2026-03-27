"""
ChainSniper - Simple blockchain event monitoring.

A builder-pattern API for watching blockchain events with automatic decoding.
"""

import asyncio
from typing import Any, Optional, Union, List
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.poll_listener import HttpListener
from chain_sniper.filters.dynamic_filter import DynamicFilter
from chain_sniper.types import EventCallback, BlockCallback, ErrorCallback, FilterFn


class ChainSniper:
    """
    Builder for creating blockchain event listeners.

    Example:
        sniper = (
            ChainSniper("wss://rpc.example.com")
            .watch(abi=erc20_abi, address="0x...", event="Transfer")
            .on_event(lambda log: print(log["args"]))
        )
        await sniper.start()
    """

    def __init__(self, rpc_url: str):
        """
        Initialize ChainSniper with RPC URL.

        Args:
            rpc_url: WebSocket or HTTP RPC URL. Auto-detects listener type.
        """
        self.rpc_url = rpc_url
        self._listener: Optional[Union[WebSocketListener, HttpListener]] = None
        self._filters: List[Any] = []
        self._event_callbacks: List[EventCallback] = []
        self._block_callbacks: List[BlockCallback] = []
        self._error_callbacks: List[ErrorCallback] = []
        self._block_detail = "full_block"
        self._poll_interval = 2.0

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

        Returns:
            Self for chaining
        """
        if not self._listener:
            self._create_listener()

        if topics:
            # Raw topics - no decoding
            self._listener.add_abi_log_filter(address=address, topics=topics)
        elif abi and event:
            # ABI + event - auto decoding
            self._listener.add_abi_log_filter(
                abi=abi, address=address, event_name=event
            )
        else:
            raise ValueError("Either provide topics or both abi and event")

        return self

    def filter(self, filter_obj: Optional[Any] = None, **rules) -> "ChainSniper":
        """
        Add filtering logic.

        Args:
            filter_obj: Custom filter object, or None to create DynamicFilter
            **rules: Rules for DynamicFilter (if filter_obj is None)

        Returns:
            Self for chaining
        """
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
        """
        Register event callback for log events.

        Args:
            callback: Async function receiving decoded log dict

        Returns:
            Self for chaining
        """
        self._event_callbacks.append(callback)
        return self

    def on_block(self, callback: BlockCallback) -> "ChainSniper":
        """
        Register block callback.

        Args:
            callback: Async function receiving block dict

        Returns:
            Self for chaining
        """
        self._block_callbacks.append(callback)
        return self

    def on_error(self, callback: ErrorCallback) -> "ChainSniper":
        """
        Register error callback.

        Args:
            callback: Async function receiving Exception

        Returns:
            Self for chaining
        """
        self._error_callbacks.append(callback)
        return self

    def block_detail(self, detail: str) -> "ChainSniper":
        """
        Set block detail level.

        Args:
            detail: "header" or "full_block"

        Returns:
            Self for chaining
        """
        self._block_detail = detail
        return self

    def poll_interval(self, seconds: float) -> "ChainSniper":
        """
        Set polling interval for HTTP listener.

        Args:
            seconds: Polling interval

        Returns:
            Self for chaining
        """
        self._poll_interval = seconds
        return self

    async def start(self) -> None:
        """
        Start the listener and begin monitoring.
        """
        if not self._listener:
            self._create_listener()

        # Register all callbacks
        for callback in self._event_callbacks:
            self._listener.on("log", callback)
        for callback in self._block_callbacks:
            self._listener.on("block", callback)
        for callback in self._error_callbacks:
            self._listener.on("error", callback)

        # TODO: Apply filters to pipeline if needed

        await self._listener.start()

    def stop(self) -> None:
        """
        Stop the listener.
        """
        if self._listener:
            self._listener.stop()

    def _create_listener(self) -> None:
        """
        Create appropriate listener based on RPC URL.
        """
        if self.rpc_url.startswith("ws"):
            from chain_sniper.listener.websocket_listener import BlockDetail

            block_detail_enum = (
                BlockDetail.FULL_BLOCK
                if self._block_detail == "full_block"
                else BlockDetail.HEADER
            )
            self._listener = WebSocketListener(
                self.rpc_url, block_detail=block_detail_enum
            )
        else:
            from chain_sniper.listener.poll_listener import BlockDetail

            block_detail_enum = (
                BlockDetail.FULL_BLOCK
                if self._block_detail == "full_block"
                else BlockDetail.HEADER
            )
            self._listener = HttpListener(
                self.rpc_url,
                block_detail=block_detail_enum,
                poll_interval=self._poll_interval,
            )
