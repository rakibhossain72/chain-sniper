import asyncio
import json
import logging
from typing import Callable, Awaitable, Any
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed
from web3 import Web3
from chain_sniper.parser.log_decoder import LogDecoder


class BlockDetail(str, Enum):
    """Controls how much block data is fetched."""

    HEADER = "header"  # only the block header (newHeads subscription)
    FULL_BLOCK = "full_block"  # header + all transactions (eth_getBlockByHash)


class _IdGen:
    """Thread-safe monotonically increasing JSON-RPC id generator."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


class WebSocketListener:
    """
    Ethereum WebSocket listener with:
      • New-block subscription  (header-only *or* full block with transactions)
      • Log / event subscription (eth_subscribe → logs, filtered by address & topics)
      • Automatic reconnection with configurable back-off
      • asyncio-based event-emitter for extensible consumer code
    """

    def __init__(
        self,
        rpc_url: str,
        *,
        block_detail: BlockDetail = BlockDetail.HEADER,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 60.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.block_detail = block_detail
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.logger = logger or logging.getLogger("WebSocketListener")

        self._ids = _IdGen()
        self._running = False
        self._ws = None  # live websocket, kept for send()

        # ── Callbacks ──────────────────────────────────────────────────────
        # key → list of async callables
        self._listeners: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "block": [],
            "log": [],
            "error": [],
        }
        # Each entry: {"address": ..., "topics": ..., "sub_id": None}
        self._log_filters: list[dict] = []

        self._sub_map: dict[str, str] = {}  # sub_id → "block" | "log"

        # ABI storage for decoding: (address, topic) -> abi
        self._abi_map: dict[tuple[str | None, str | None], list] = {}
        self._log_decoder = LogDecoder()

    def on(
        self, event: str, callback: Callable[..., Awaitable[None]]
    ) -> Callable[..., Awaitable[None]]:
        """
        Register an async callback for *event*.

        Events:
            "block"  - fired for every new block (dict).
            "log"    - fired for every matched log / event (dict).
            "error"  - fired on non-fatal errors (Exception).

        Example::

            @listener.on("block")
            async def handle_block(block: dict) -> None:
                print(block["number"])
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        return callback  # allow use as a decorator

    def add_log_filter(
        self,
        address: str | list[str] | None = None,
        topics: list[str | list[str] | None] | None = None,
    ) -> None:
        """
        Queue a log/event subscription.

        Args:
            address: Contract address or list of addresses to watch.
            topics:  EVM topic filter (supports nested OR lists).

        Must be called *before* :meth:`start`.

        Example::

            listener.add_log_filter(
                address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
                topics=["0xddf252ad..."],   # Transfer(address,address,uint256)
            )
        """
        self._log_filters.append({"address": address, "topics": topics})

    def add_abi_log_filter(
        self,
        abi: list | str,
        address: str | list[str] | None = None,
        event_name: str | None = None,
    ) -> None:
        """
        Queue a log/event subscription using ABI and event name.

        Args:
            abi: Contract ABI as list or JSON string.
            address: Contract address or list of addresses to watch.
            event_name: Name of the event to filter (e.g., "Transfer").

        If event_name is provided, it will generate the topic hash from the ABI.
        If not, it subscribes to all events from the contract.
        """
        if isinstance(abi, str):
            abi = json.loads(abi)

        w3 = Web3()
        contract = w3.eth.contract(abi=abi)

        topics = None
        if event_name:
            event = getattr(contract.events, event_name)()
            # Get the event signature topic
            topics = [event.topic]

        # Store ABI for decoding
        if address and isinstance(address, str):
            addresses = [address]
        elif address and isinstance(address, list):
            addresses = address
        else:
            addresses = [None]  # No address filter

        for addr in addresses:
            if topics:
                for topic in topics:
                    self._abi_map[(addr, topic)] = abi
            else:
                # If no specific event, store for all events from this address
                self._abi_map[(addr, None)] = abi

        self.add_log_filter(address=address, topics=topics)

    async def _emit(self, event: str, payload: Any) -> None:
        for cb in self._listeners.get(event, []):
            try:
                await cb(payload)
            except Exception as exc:
                self.logger.exception("Callback raised for event '%s': %s", event, exc)

    async def _rpc(self, ws, method: str, params: list) -> Any:
        """Send a JSON-RPC request and return the 'result' field."""
        req_id = self._ids.next()
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params,
                }
            )
        )
        # Drain until we get the matching response (subscriptions may arrive first)
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"RPC error: {msg['error']}")
                return msg["result"]
            # Could be a subscription message that arrived before the response
            await self._dispatch(msg)

    async def _subscribe_heads(self, ws) -> str:
        sub_id = await self._rpc(ws, "eth_subscribe", ["newHeads"])
        self._sub_map[sub_id] = "block"
        self.logger.info("Subscribed to newHeads  → sub_id=%s", sub_id)
        return sub_id

    async def _subscribe_logs(self, ws) -> None:
        for flt in self._log_filters:
            params: dict = {}
            if flt["address"]:
                params["address"] = flt["address"]
            if flt["topics"]:
                params["topics"] = flt["topics"]
            sub_id = await self._rpc(ws, "eth_subscribe", ["logs", params])
            self._sub_map[sub_id] = "log"
            self.logger.info(
                "Subscribed to logs     → sub_id=%s  filter=%s", sub_id, params
            )

    async def _fetch_full_block(self, ws, block_hash: str) -> dict:
        """Fetch the full block (including all transactions) by hash."""
        return await self._rpc(ws, "eth_getBlockByHash", [block_hash, True])

    async def _dispatch(self, msg: dict) -> None:
        """Route an incoming subscription notification to the right event."""
        if "params" not in msg:
            return
        sub_id = msg["params"].get("subscription")
        result = msg["params"].get("result")
        event = self._sub_map.get(sub_id)

        if event == "block":
            if self.block_detail == BlockDetail.FULL_BLOCK and self._ws:
                block_hash = result.get("hash")
                if block_hash:
                    try:
                        result = await self._fetch_full_block(self._ws, block_hash)
                    except Exception as exc:
                        self.logger.warning(
                            "Could not fetch full block %s: %s", block_hash, exc
                        )
            await self._emit("block", result)

        elif event == "log":
            # Decode log if ABI is available
            decoded_log = self._decode_log(result)
            await self._emit("log", decoded_log)

    async def start(self) -> None:
        """Connect, subscribe, and run until :meth:`stop` is called."""
        self._running = True
        delay = self.reconnect_delay
        # log
        self.logger.info("Starting WebSocketListener")

        while self._running:
            try:
                async with websockets.connect(self.rpc_url) as ws:
                    self._ws = ws
                    self._sub_map.clear()
                    delay = self.reconnect_delay  # reset back-off on success

                    await self._subscribe_heads(ws)
                    await self._subscribe_logs(ws)

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            await self._dispatch(json.loads(raw))
                        except Exception as exc:
                            self.logger.error("Dispatch error: %s", exc)
                            await self._emit("error", exc)

            except ConnectionClosed as exc:
                self.logger.warning("Connection closed: %s", exc)
            except Exception as exc:
                self.logger.error("Listener error: %s", exc)
                await self._emit("error", exc)
            finally:
                self._ws = None

            if self._running:
                self.logger.info("Reconnecting in %.1fs…", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def _decode_log(self, log: dict) -> dict:
        """Decode log using stored ABI if available."""
        address = log.get("address")
        topics = log.get("topics", [])
        if topics:
            topic = topics[0]
            # Try exact match
            abi = self._abi_map.get((address, topic))
            if abi:
                return self._log_decoder.decode_log(log, abi)
            # Try address only
            abi = self._abi_map.get((address, None))
            if abi:
                return self._log_decoder.decode_log(log, abi)
        return log

    def stop(self) -> None:
        """Signal the listener to stop after the current iteration."""
        self._running = False
        self.logger.info("Listener stop requested.")
