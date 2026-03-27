import asyncio
import json
import logging
from typing import Callable, Awaitable, Any
from enum import Enum
import aiohttp
from web3 import Web3
from chain_sniper.parser.log_decoder import LogDecoder


class BlockDetail(str, Enum):
    """Controls how much block data is fetched."""

    HEADER = "header"  # only the block header (eth_getBlockByNumber, no txs)
    FULL_BLOCK = (
        "full_block"  # header + all transactions (eth_getBlockByNumber, full txs)
    )


class _IdGen:
    """Thread-safe monotonically increasing JSON-RPC id generator."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


class HttpListener:
    """
    Ethereum HTTP polling listener with:
      • New-block polling     (header-only *or* full block with transactions)
      • Log / event polling   (eth_getLogs, filtered by address & topics)
      • Automatic reconnection with configurable back-off
      • asyncio-based event-emitter — identical interface to WebSocketListener

    Drop-in replacement for WebSocketListener when a WebSocket endpoint is
    unavailable.  Both classes share the same public API:
      - constructor keyword args  (block_detail, reconnect_delay, max_reconnect_delay, logger)
      - .on(event, callback)
      - .add_log_filter(address, topics)
      - await .start()
      - .stop()

    Events emitted: "block", "log", "error"
    """

    def __init__(
        self,
        rpc_url: str,
        *,
        block_detail: BlockDetail = BlockDetail.HEADER,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 60.0,
        poll_interval: float = 2.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.block_detail = block_detail
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.poll_interval = poll_interval
        self.logger = logger or logging.getLogger("HttpListener")

        self._ids = _IdGen()
        self._running = False
        self._session: aiohttp.ClientSession | None = (
            None  # live session, kept for _rpc()
        )

        # ── Callbacks ──────────────────────────────────────────────────────
        # key → list of async callables
        self._listeners: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "block": [],
            "log": [],
            "error": [],
        }
        # Each entry: {"address": ..., "topics": ..., "filter_id": None}
        self._log_filters: list[dict] = []

        # ABI storage for decoding: (address, topic) -> abi
        self._abi_map: dict[tuple[str | None, str | None], list] = {}
        self._log_decoder = LogDecoder()

        # ── State ──────────────────────────────────────────────────────────
        self._last_block_number: int | None = (
            None  # highest block we've already emitted
        )
        self._filter_ids: list[str] = []  # eth_newFilter IDs (if node supports it)
        self._use_filter_api = True  # flip to False if node rejects eth_newFilter

    # ──────────────────────────────────────────────────────────────────────
    # Public API  (identical signatures to WebSocketListener)
    # ──────────────────────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable[..., Awaitable[None]]) -> Callable:
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
        self._log_filters.append(
            {"address": address, "topics": topics, "filter_id": None}
        )

    def add_abi_log_filter(
        self,
        abi: list | str | None = None,
        address: str | list[str] | None = None,
        event_name: str | None = None,
        topics: list[str | list[str] | None] | None = None,
    ) -> None:
        """
        Queue a log/event subscription using ABI/event name or topic hashes.

        Args:
            abi: Contract ABI as list or JSON string (optional if using topics).
            address: Contract address or list of addresses to watch.
            event_name: Name of the event to filter (e.g., "Transfer").
            topics: EVM topic filter (alternative to abi+event_name).

        When using abi+event_name, logs will be automatically decoded.
        When using topics, logs will remain raw.
        """
        if topics is not None:
            # Use provided topics - no decoding
            self.add_log_filter(address=address, topics=topics)
            return

        if abi is None or event_name is None:
            raise ValueError("Either provide topics or both abi and event_name")

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
            # Normalize address to lowercase for consistent lookup
            addr_lower = addr.lower() if addr else None
            if topics:
                # Store ABI for each topic (assuming topics[0] is event signature)
                for topic in topics:
                    if isinstance(topic, str):
                        self._abi_map[(addr_lower, topic)] = abi
                    elif isinstance(topic, list):
                        # Handle nested OR lists
                        for sub_topic in topic:
                            if isinstance(sub_topic, str):
                                self._abi_map[(addr_lower, sub_topic)] = abi
            else:
                # If no specific event, store for all events from this address
                self._abi_map[(addr_lower, None)] = abi

        self.add_log_filter(address=address, topics=topics)

    async def start(self) -> None:
        """Connect, subscribe, and run until :meth:`stop` is called."""
        self._running = True
        delay = self.reconnect_delay

        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    self._session = session
                    delay = self.reconnect_delay  # reset back-off on successful connect

                    # Initialise chain state on (re-)connect
                    self._last_block_number = await self._get_latest_block_number()
                    self.logger.info(
                        "Connected to %s  latest_block=%s",
                        self.rpc_url,
                        hex(self._last_block_number),
                    )

                    # Set up log filters (prefer eth_newFilter, fall back to eth_getLogs scan)
                    await self._setup_log_filters()

                    # Main polling loop
                    while self._running:
                        await self._poll_blocks()
                        await self._poll_logs()
                        await asyncio.sleep(self.poll_interval)

            except aiohttp.ClientError as exc:
                self.logger.warning("HTTP connection error: %s", exc)
            except Exception as exc:
                self.logger.error("Listener error: %s", exc)
                await self._emit("error", exc)
            finally:
                self._session = None
                self._filter_ids.clear()

            if self._running:
                self.logger.info("Reconnecting in %.1fs…", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def _decode_log(self, log: dict) -> dict:
        """Decode log using stored ABI if available."""
        address = log.get("address")
        address_lower = address.lower() if address else None
        topics = log.get("topics", [])
        if topics:
            topic = topics[0]
            # Try exact match
            abi = self._abi_map.get((address_lower, topic))
            if abi:
                return self._log_decoder.decode_log(log, abi)
            # Try address only
            abi = self._abi_map.get((address_lower, None))
            if abi:
                return self._log_decoder.decode_log(log, abi)
        return log

    def stop(self) -> None:
        """Signal the listener to stop after the current iteration."""
        self._running = False
        self.logger.info("Listener stop requested.")

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _emit(self, event: str, payload: Any) -> None:
        for cb in self._listeners.get(event, []):
            try:
                await cb(payload)
            except Exception as exc:
                self.logger.exception("Callback raised for event '%s': %s", event, exc)

    async def _rpc(self, method: str, params: list) -> Any:
        """Send a JSON-RPC POST request and return the 'result' field."""
        if self._session is None:
            raise RuntimeError("No active HTTP session")

        payload = {
            "jsonrpc": "2.0",
            "id": self._ids.next(),
            "method": method,
            "params": params,
        }
        async with self._session.post(
            self.rpc_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            resp.raise_for_status()
            msg = await resp.json(content_type=None)

        if "error" in msg:
            raise RuntimeError(f"RPC error: {msg['error']}")
        return msg["result"]

    async def _get_latest_block_number(self) -> int:
        hex_num = await self._rpc("eth_blockNumber", [])
        return int(hex_num, 16)

    async def _get_block_by_number(self, block_number: int) -> dict:
        """Fetch a block by number. Includes full txs iff block_detail == FULL_BLOCK."""
        full_tx = self.block_detail == BlockDetail.FULL_BLOCK
        return await self._rpc(
            "eth_getBlockByNumber",
            [hex(block_number), full_tx],
        )

    # ── Block polling ──────────────────────────────────────────────────────

    async def _poll_blocks(self) -> None:
        try:
            latest = await self._get_latest_block_number()
        except Exception as exc:
            self.logger.error("eth_blockNumber failed: %s", exc)
            await self._emit("error", exc)
            return

        if self._last_block_number is None:
            self._last_block_number = latest
            return

        for block_num in range(self._last_block_number + 1, latest + 1):
            try:
                block = await self._get_block_by_number(block_num)
                if block:
                    await self._emit("block", block)
                    self.logger.debug("Emitted block %s", hex(block_num))
            except Exception as exc:
                self.logger.warning("Could not fetch block %s: %s", hex(block_num), exc)
                await self._emit("error", exc)

        self._last_block_number = latest

    # ── Log polling ────────────────────────────────────────────────────────

    async def _setup_log_filters(self) -> None:
        """
        Try to install eth_newFilter for each log filter.
        Falls back to raw eth_getLogs scanning if the node rejects filter creation.
        """
        self._filter_ids.clear()
        if not self._log_filters:
            return

        for flt in self._log_filters:
            flt["filter_id"] = None  # reset on reconnect

        # Probe whether eth_newFilter is supported
        try:
            probe_params: dict = {}
            if self._log_filters[0]["address"]:
                probe_params["address"] = self._log_filters[0]["address"]
            if self._log_filters[0]["topics"]:
                probe_params["topics"] = self._log_filters[0]["topics"]
            probe_params["fromBlock"] = "latest"
            filter_id = await self._rpc("eth_newFilter", [probe_params])
            self._log_filters[0]["filter_id"] = filter_id
            self._filter_ids.append(filter_id)
            self._use_filter_api = True
            self.logger.info("Using eth_newFilter API for log polling")

            # Install remaining filters
            for flt in self._log_filters[1:]:
                params: dict = {}
                if flt["address"]:
                    params["address"] = flt["address"]
                if flt["topics"]:
                    params["topics"] = flt["topics"]
                params["fromBlock"] = "latest"
                fid = await self._rpc("eth_newFilter", [params])
                flt["filter_id"] = fid
                self._filter_ids.append(fid)
                self.logger.info(
                    "Installed eth_newFilter → filter_id=%s  params=%s", fid, params
                )

        except Exception:
            self._use_filter_api = False
            self.logger.info(
                "eth_newFilter not supported — falling back to eth_getLogs range scanning"
            )

    async def _poll_logs(self) -> None:
        if not self._log_filters:
            return

        if self._use_filter_api:
            await self._poll_logs_via_filter()
        else:
            await self._poll_logs_via_getlogs()

    async def _poll_logs_via_filter(self) -> None:
        """Drain new entries from each eth_newFilter via eth_getFilterChanges."""
        for flt in self._log_filters:
            filter_id = flt.get("filter_id")
            if not filter_id:
                continue
            try:
                logs = await self._rpc("eth_getFilterChanges", [filter_id])
                for log in logs or []:
                    decoded_log = self._decode_log(log)
                    await self._emit("log", decoded_log)
            except Exception as exc:
                self.logger.warning(
                    "eth_getFilterChanges failed for filter %s: %s — switching to eth_getLogs",
                    filter_id,
                    exc,
                )
                # Filter may have expired; switch to fallback method
                self._use_filter_api = False
                # Don't emit error for filter expiration, it's expected
                return

    async def _poll_logs_via_getlogs(self) -> None:
        """
        Fetch logs via eth_getLogs for the block range we haven't processed yet.
        Used when the node does not support stateful filters.
        """
        if self._last_block_number is None:
            return

        from_block = hex(self._last_block_number)
        to_block = "latest"

        for flt in self._log_filters:
            params: dict = {"fromBlock": from_block, "toBlock": to_block}
            if flt["address"]:
                params["address"] = flt["address"]
            if flt["topics"]:
                params["topics"] = flt["topics"]
            try:
                logs = await self._rpc("eth_getLogs", [params])
                for log in logs or []:
                    decoded_log = self._decode_log(log)
                    await self._emit("log", decoded_log)
            except Exception as exc:
                self.logger.error("eth_getLogs failed: %s", exc)
                await self._emit("error", exc)
