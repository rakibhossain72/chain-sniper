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
    ) -> None:
        self.rpc_url = rpc_url
        self.block_detail = block_detail
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.poll_interval = poll_interval
        self.chain_id = chain_id
        self.logger = logger or logging.getLogger("HttpListener")

        self._running = False
        self._w3: AsyncWeb3 | None = None

        self._listeners: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "block": [],
            "log": [],
            "error": [],
        }
        self._log_filters: list[dict] = []
        self._abi_filter = ABIFilterRegistry()

        self._last_block_number: int | None = None
        self._filter_ids: list[str] = []
        self._use_filter_api = True

    def on(
        self,
        event: str,
        callback: Callable[..., Awaitable[None]],
    ) -> Callable:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        return callback

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

    async def start(self) -> None:
        self._running = True
        delay = self.reconnect_delay

        while self._running:
            try:
                provider = AsyncHTTPProvider(self.rpc_url)
                self._w3 = AsyncWeb3(provider)

                # Inject POA middleware if the chain needs it
                if needs_poa_middleware(self.chain_id):
                    self._w3.middleware_onion.inject(
                        ExtraDataToPOAMiddleware, layer=0
                    )
                    self.logger.debug(
                        "Injected ExtraDataToPOAMiddleware "
                        "for chain_id=%s",
                        self.chain_id
                    )

                delay = self.reconnect_delay

                block_num = await self._w3.eth.block_number
                self._last_block_number = block_num
                self.logger.info(
                    "Connected to %s  latest_block=%s",
                    self.rpc_url,
                    hex(self._last_block_number),
                )

                await self._setup_log_filters()

                while self._running:
                    await self._poll_blocks()
                    await self._poll_logs()
                    await asyncio.sleep(self.poll_interval)

            except Exception as exc:
                self.logger.error("Listener error: %s", exc)
                await self._emit("error", exc)
            finally:
                if self._w3:
                    await self._w3.provider.disconnect()
                    self._w3 = None
                self._filter_ids.clear()

            if self._running:
                self.logger.info("Reconnecting in %.1fs...", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def stop(self) -> None:
        self._running = False
        self.logger.info("Listener stop requested.")

    def _decode_log(self, log: dict) -> dict:
        return self._abi_filter.decode_log(log)

    async def _emit(self, event: str, payload: Any) -> None:
        for cb in self._listeners.get(event, []):
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

    async def _get_block_by_number(self, block_number: int) -> dict:
        if self._w3 is None:
            raise RuntimeError("No active Web3 connection")
        full_tx = self.block_detail == BlockDetail.FULL_BLOCK
        return await self._w3.eth.get_block(
            block_number, full_transactions=full_tx
        )

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
                self.logger.warning(
                    "Could not fetch block %s: %s", hex(block_num), exc
                )
                await self._emit("error", exc)

        self._last_block_number = latest

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
                    fid,
                    params,
                )

        except Exception:
            self._use_filter_api = False
            self.logger.info(
                "eth_newFilter not supported -- falling back to eth_getLogs"
            )

    async def _poll_logs(self) -> None:
        if not self._log_filters:
            return

        if self._use_filter_api:
            await self._poll_logs_via_filter()
        else:
            await self._poll_logs_via_getlogs()

    async def _poll_logs_via_filter(self) -> None:
        for flt in self._log_filters:
            filter_id = flt.get("filter_id").filter_id
            if not filter_id:
                continue
            try:
                logs = await self._w3.eth.get_filter_changes(filter_id)
                for log in logs or []:
                    await self._emit("log", self._decode_log(log))
            except Exception as exc:
                self.logger.warning(
                    "eth_getFilterChanges failed for filter %s: %s"
                    " -- switching to eth_getLogs",
                    filter_id,
                    exc,
                )
                self._use_filter_api = False
                return

    async def _poll_logs_via_getlogs(self) -> None:
        if self._last_block_number is None:
            return

        from_block = self._last_block_number

        for flt in self._log_filters:
            params: dict = {"fromBlock": from_block, "toBlock": "latest"}
            if flt["address"]:
                params["address"] = flt["address"]
            if flt["topics"]:
                params["topics"] = flt["topics"]
            try:
                logs = await self._w3.eth.get_logs(params)
                for log in logs or []:
                    await self._emit("log", self._decode_log(log))
            except Exception as exc:
                self.logger.error("eth_getLogs failed: %s", exc)
                await self._emit("error", exc)
