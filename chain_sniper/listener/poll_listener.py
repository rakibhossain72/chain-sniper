import asyncio
import logging
from typing import Callable, Awaitable, Any

from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware

from chain_sniper.listener.common import BlockDetail, needs_poa_middleware
from chain_sniper.utils.abi_filter import ABIFilterRegistry


class HttpListener:
    def __init__(
        self,
        rpc_url: str,
        *,
        block_detail: BlockDetail = BlockDetail.HEADER,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 60.0,
        poll_interval: float = 2.0,
        chain_id: int | None = None,
        logger: logging.Logger | None = None,
        BLOCK_COMPLETENESS_RETRIES: int = 5,
        BLOCK_COMPLETENESS_INTERVAL: float = 0.3,
        log_filter=None,
        transaction_filter=None,
    ) -> None:
        self.rpc_url = rpc_url
        self.block_detail = block_detail
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.poll_interval = poll_interval
        self.chain_id = chain_id
        self.logger = logger or logging.getLogger("HttpListener")
        self.BLOCK_COMPLETENESS_RETRIES = BLOCK_COMPLETENESS_RETRIES
        self.BLOCK_COMPLETENESS_INTERVAL = BLOCK_COMPLETENESS_INTERVAL

        # New split filter references
        self._log_filter = log_filter          # LogFilter instance (or None)
        self._tx_filter = transaction_filter   # TransactionFilter (or None)

        self._running = False
        self._w3: AsyncWeb3 | None = None

        self._listeners: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "block": [],
            "transaction": [],
            "log": [],
            "reorg": [],
            "error": [],
        }

        # Legacy manual log filters (kept for backward compat)
        self._log_filters: list[dict] = []
        self._abi_filter = ABIFilterRegistry()

        self._last_block_number: int | None = None
        self._last_block_hash: str | None = None
        self._filter_ids: list[str] = []
        self._use_filter_api = True

        # LogFilter-managed filter specs: maps sub_id -> {filter_id, spec}
        self._log_filter_map: dict[str, dict] = {}

    # Public API
    def on(
        self,
        event: str,
        callback: Callable[..., Awaitable[None]],
    ) -> Callable:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        return callback

    #  Legacy log filter API 

    def add_log_filter(
        self,
        address: str | list[str] | None = None,
        topics: list[str | list[str] | None] | None = None,
    ) -> None:
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
        if topics is not None:
            self.add_log_filter(address=address, topics=topics)
            return

        if abi is None or event_name is None:
            raise ValueError(
                "Either provide topics or both abi and event_name"
            )

        generated_topics = self._abi_filter.register_abi_filter(
            abi=abi, address=address, event_name=event_name
        )
        self.add_log_filter(address=address, topics=generated_topics)

    #  LogFilter ↔ listener binding 

    def _bind_log_filter(self) -> None:
        """Bind the LogFilter so new subscriptions trigger eth_newFilter."""
        if self._log_filter is None:
            return
        self._log_filter.bind_listener(
            on_subscribe=self._on_log_subscribe,
            on_unsubscribe=self._on_log_unsubscribe,
        )

    def _unbind_log_filter(self) -> None:
        if self._log_filter is not None:
            self._log_filter.unbind_listener()

    async def _on_log_subscribe(self, spec: dict) -> None:
        """Called by LogFilter when a new subscription is added at runtime."""
        if self._w3 is None:
            return
        params: dict = {"fromBlock": "latest"}
        if spec.get("address"):
            params["address"] = spec["address"]
        if spec.get("topics"):
            params["topics"] = spec["topics"]

        if self._use_filter_api:
            try:
                filter_id = await self._w3.eth.filter(params)
                spec["filter_id"] = filter_id
                self._log_filter_map[spec["id"]] = {
                    "filter_id": filter_id,
                    "spec": spec,
                }
                self._filter_ids.append(filter_id)
                self.logger.info(
                    "Installed eth_newFilter for sub_id=%s filter_id=%s params=%s",
                    spec["id"], filter_id, params,
                )
            except Exception as exc:
                self.logger.error(
                    "eth_newFilter failed for sub_id=%s: %s — will use eth_getLogs",
                    spec["id"], exc,
                )
                # Fallback: store spec for getLogs polling
                self._log_filter_map[spec["id"]] = {
                    "filter_id": None,
                    "spec": spec,
                }
        else:
            # Filter API not available — store spec for getLogs polling
            self._log_filter_map[spec["id"]] = {
                "filter_id": None,
                "spec": spec,
            }

    async def _on_log_unsubscribe(self, spec: dict) -> None:
        """Called by LogFilter when a subscription is removed at runtime."""
        entry = self._log_filter_map.pop(spec["id"], None)
        if entry and entry.get("filter_id") and self._w3:
            try:
                await self._w3.eth.uninstall_filter(entry["filter_id"])
                self.logger.info(
                    "Uninstalled filter for sub_id=%s", spec["id"],
                )
            except Exception as exc:
                self.logger.error("Uninstall filter error: %s", exc)
            if entry["filter_id"] in self._filter_ids:
                self._filter_ids.remove(entry["filter_id"])

    async def _setup_log_filter_specs(self) -> None:
        """Install eth_newFilter for all existing LogFilter specs (on connect)."""
        if self._log_filter is None:
            return
        for spec in self._log_filter.get_subscriptions():
            await self._on_log_subscribe(spec)

    #  Lifecycle 

    async def start(self) -> None:
        self._running = True
        delay = self.reconnect_delay

        while self._running:
            try:
                provider = AsyncHTTPProvider(self.rpc_url)
                self._w3 = AsyncWeb3(provider)

                if needs_poa_middleware(self.chain_id):
                    self._w3.middleware_onion.inject(
                        ExtraDataToPOAMiddleware, layer=0
                    )
                    self.logger.debug(
                        "Injected ExtraDataToPOAMiddleware for chain_id=%s",
                        self.chain_id,
                    )

                delay = self.reconnect_delay

                block_num = await self._w3.eth.block_number
                self._last_block_number = block_num
                self._last_block_hash = None
                self.logger.info(
                    "Connected to %s  latest_block=%s",
                    self.rpc_url,
                    hex(self._last_block_number),
                )

                # Setup legacy manual log filters
                await self._setup_log_filters()

                # Setup LogFilter-managed specs and bind for runtime adds
                await self._setup_log_filter_specs()
                self._bind_log_filter()

                while self._running:
                    await self._poll_blocks()
                    await self._poll_logs()
                    await asyncio.sleep(self.poll_interval)

            except Exception as exc:
                self.logger.error("Listener error: %s", exc)
                asyncio.create_task(self._emit("error", exc))
            finally:
                self._unbind_log_filter()
                if self._w3:
                    await self._w3.provider.disconnect()
                    self._w3 = None
                self._filter_ids.clear()
                self._log_filter_map.clear()

            if self._running:
                self.logger.info("Reconnecting in %.1fs…", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def stop(self) -> None:
        self._running = False
        self.logger.info("Listener stop requested.")

    #  Internal helpers 

    def _decode_log(self, log: dict) -> dict:
        decoded = self._abi_filter.decode_log(log)
        if decoded is not log:
            return decoded
        if self._log_filter is not None:
            return self._log_filter.decode_log(log)
        return log

    async def _emit(self, event: str, payload: Any) -> None:
        for cb in self._listeners.get(event, []):
            asyncio.create_task(self._safe_call(cb, event, payload))

    async def _safe_call(
        self, cb: Callable[..., Awaitable[None]], event: str, payload: Any
    ) -> None:
        try:
            await cb(payload)
        except Exception as exc:
            self.logger.exception(
                "Callback raised for event '%s': %s", event, exc
            )

    async def _get_latest_block_number(self) -> int:
        if self._w3 is None:
            raise RuntimeError("No active Web3 connection")
        return await self._w3.eth.block_number

    async def _get_block_by_number(self, block_number: int) -> dict | None:
        if self._w3 is None:
            raise RuntimeError("No active Web3 connection")

        full_tx = self.block_detail == BlockDetail.FULL_BLOCK
        prev_tx_count: int | None = None
        block = None

        for attempt in range(self.BLOCK_COMPLETENESS_RETRIES):
            try:
                block = await self._w3.eth.get_block(
                    block_number, full_transactions=full_tx
                )
            except Exception as exc:
                self.logger.warning(
                    "get_block(%s) attempt %d failed: %s",
                    hex(block_number), attempt + 1, exc,
                )
                await asyncio.sleep(self.BLOCK_COMPLETENESS_INTERVAL)
                continue

            tx_count = len(block.get("transactions", []))
            if tx_count == prev_tx_count:
                return block

            prev_tx_count = tx_count
            if attempt < self.BLOCK_COMPLETENESS_RETRIES - 1:
                await asyncio.sleep(self.BLOCK_COMPLETENESS_INTERVAL)

        self.logger.warning(
            "Block %s tx count never stabilised; emitting with %d txs",
            hex(block_number),
            len(block.get("transactions", [])) if block else 0,
        )
        return block

    async def _poll_blocks(self) -> None:
        try:
            latest = await self._get_latest_block_number()
        except Exception as exc:
            self.logger.error("eth_blockNumber failed: %s", exc)
            asyncio.create_task(self._emit("error", exc))
            return

        if self._last_block_number is None:
            self._last_block_number = latest
            return

        for block_num in range(self._last_block_number + 1, latest + 1):
            try:
                block = await self._get_block_by_number(block_num)
                if not block:
                    continue

                # Reorg detection
                parent_hash = block.get("parentHash")
                if isinstance(parent_hash, bytes):
                    parent_hash = "0x" + parent_hash.hex()

                if (
                    self._last_block_hash is not None
                    and parent_hash != self._last_block_hash
                ):
                    self.logger.warning(
                        "Reorg detected at block %s: expected_parent=%s "
                        "actual_parent=%s",
                        hex(block_num),
                        self._last_block_hash,
                        parent_hash,
                    )
                    asyncio.create_task(
                        self._emit("reorg", {
                            "detected_at_block": block_num,
                            "expected_parent": self._last_block_hash,
                            "actual_parent": parent_hash,
                        })
                    )

                block_hash = block.get("hash")
                if isinstance(block_hash, bytes):
                    block_hash = "0x" + block_hash.hex()
                self._last_block_hash = block_hash

                asyncio.create_task(self._emit("block", block))
                self.logger.debug("Emitted block %s", hex(block_num))

                if self.block_detail == BlockDetail.FULL_BLOCK:
                    for tx in block.get("transactions", []):
                        asyncio.create_task(self._emit("transaction", tx))

            except Exception as exc:
                self.logger.warning(
                    "Could not fetch block %s: %s", hex(block_num), exc
                )
                asyncio.create_task(self._emit("error", exc))

        self._last_block_number = latest

    #  Legacy log filter setup 

    async def _setup_log_filters(self) -> None:
        self._filter_ids.clear()
        if not self._log_filters:
            return

        for flt in self._log_filters:
            flt["filter_id"] = None

        try:
            first = self._log_filters[0]
            probe_params: dict = {}
            if first["address"]:
                probe_params["address"] = first["address"]
            if first["topics"]:
                probe_params["topics"] = first["topics"]
            probe_params["fromBlock"] = "latest"

            filter_id = await self._w3.eth.filter(probe_params)
            first["filter_id"] = filter_id
            self._filter_ids.append(filter_id)
            self._use_filter_api = True
            self.logger.info("Using eth_newFilter API for log polling")

            for flt in self._log_filters[1:]:
                params: dict = {}
                if flt["address"]:
                    params["address"] = flt["address"]
                if flt["topics"]:
                    params["topics"] = flt["topics"]
                params["fromBlock"] = "latest"
                fid = await self._w3.eth.filter(params)
                flt["filter_id"] = fid
                self._filter_ids.append(fid)
                self.logger.info(
                    "Installed eth_newFilter -> filter_id=%s  params=%s",
                    fid, params,
                )

        except Exception:
            self._use_filter_api = False
            self.logger.info(
                "eth_newFilter not supported — falling back to eth_getLogs"
            )

    #  Log polling 

    async def _poll_logs(self) -> None:
        has_legacy = bool(self._log_filters)
        has_managed = bool(self._log_filter_map)
        if not has_legacy and not has_managed and self._log_filter is None:
            return

        if self._use_filter_api:
            await self._poll_logs_via_filter()
        else:
            await self._poll_logs_via_getlogs()

    async def _poll_logs_via_filter(self) -> None:
        """Poll using eth_getFilterChanges for both legacy and LogFilter specs."""
        # Legacy filters
        for flt in self._log_filters:
            filter_id = flt.get("filter_id")
            if not filter_id:
                continue
            fid = filter_id.filter_id if hasattr(filter_id, 'filter_id') else filter_id
            try:
                logs = await self._w3.eth.get_filter_changes(fid)
                for log in logs or []:
                    decoded = self._decode_log(log)
                    asyncio.create_task(self._emit("log", decoded))
            except Exception as exc:
                self.logger.warning(
                    "eth_getFilterChanges failed for filter %s: %s"
                    " — switching to eth_getLogs",
                    fid, exc,
                )
                self._use_filter_api = False
                return

        # LogFilter-managed filters
        for sub_id, entry in list(self._log_filter_map.items()):
            filter_id = entry.get("filter_id")
            if not filter_id:
                continue
            fid = filter_id.filter_id if hasattr(filter_id, 'filter_id') else filter_id
            try:
                logs = await self._w3.eth.get_filter_changes(fid)
                for log in logs or []:
                    decoded = self._decode_log(log)
                    # Apply post-filter rules if present
                    if self._log_filter and self._log_filter.has_rules:
                        if not self._log_filter.match(decoded):
                            continue
                    asyncio.create_task(self._emit("log", decoded))
            except Exception as exc:
                self.logger.warning(
                    "eth_getFilterChanges failed for managed filter sub_id=%s: %s"
                    " — switching to eth_getLogs",
                    sub_id, exc,
                )
                self._use_filter_api = False
                return

    async def _poll_logs_via_getlogs(self) -> None:
        if self._last_block_number is None:
            return

        from_block = self._last_block_number

        # Legacy filters
        for flt in self._log_filters:
            params: dict = {"fromBlock": from_block, "toBlock": "latest"}
            if flt["address"]:
                params["address"] = flt["address"]
            if flt["topics"]:
                params["topics"] = flt["topics"]
            try:
                logs = await self._w3.eth.get_logs(params)
                for log in logs or []:
                    decoded = self._decode_log(log)
                    asyncio.create_task(self._emit("log", decoded))
            except Exception as exc:
                self.logger.error("eth_getLogs failed: %s", exc)
                asyncio.create_task(self._emit("error", exc))

        # LogFilter-managed specs (getLogs fallback)
        if self._log_filter is not None:
            for spec in self._log_filter.get_subscriptions():
                params = {"fromBlock": from_block, "toBlock": "latest"}
                if spec.get("address"):
                    params["address"] = spec["address"]
                if spec.get("topics"):
                    params["topics"] = spec["topics"]
                try:
                    logs = await self._w3.eth.get_logs(params)
                    for log in logs or []:
                        decoded = self._decode_log(log)
                        # Apply post-filter rules
                        if self._log_filter.has_rules:
                            if not self._log_filter.match(decoded):
                                continue
                        asyncio.create_task(self._emit("log", decoded))
                except Exception as exc:
                    self.logger.error(
                        "eth_getLogs failed for sub_id=%s: %s", spec["id"], exc,
                    )
                    asyncio.create_task(self._emit("error", exc))
