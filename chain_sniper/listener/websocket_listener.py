import asyncio
import logging
from typing import Callable, Awaitable, Any

from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider
from web3.datastructures import AttributeDict
from web3.middleware import ExtraDataToPOAMiddleware

from chain_sniper.listener.common import BlockDetail, needs_poa_middleware
from chain_sniper.parser.block_fetcher import BlockFetcher
from chain_sniper.parser.block_processor import BlockProcessor
from chain_sniper.parser.event_dispatcher import EventDispatcher
from chain_sniper.utils.abi_filter import ABIFilterRegistry


class WebSocketListener:
    def __init__(
        self,
        rpc_url: str,
        *,
        block_detail: BlockDetail = BlockDetail.HEADER,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 60.0,
        chain_id: int | None = None,
        logger: logging.Logger | None = None,
        HEADER_QUEUE_MAX: int = 256
    ) -> None:
        self.rpc_url = rpc_url
        self.block_detail = block_detail
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.chain_id = chain_id
        self.logger = logger or logging.getLogger("WebSocketListener")
        self.HEADER_QUEUE_MAX = HEADER_QUEUE_MAX

        self._running = False
        self._w3: AsyncWeb3 | None = None

        self._listeners: dict[
            str, list[Callable[..., Awaitable[None]]]
        ] = {
            "block": [],
            "transaction": [],
            "log": [],
            "reorg": [],
            "error": [],
        }
        self._log_filters: list[dict] = []
        self._abi_filter = ABIFilterRegistry()

        self._subscription_ids: list[str] = []

        self._header_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.HEADER_QUEUE_MAX
        )
        self._worker_task: asyncio.Task | None = None

        self._block_fetcher: BlockFetcher | None = None
        self._block_processor: BlockProcessor = BlockProcessor(self.logger)
        self._dispatcher: EventDispatcher = EventDispatcher(
            self._listeners, self.logger
        )

    def on(
        self, event: str, callback: Callable[..., Awaitable[None]]
    ) -> Callable[..., Awaitable[None]]:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        return callback

    def add_log_filter(
        self,
        address: str | list[str] | None = None,
        topics: list[str | list[str] | None] | None = None,
    ) -> None:
        self._log_filters.append({"address": address, "topics": topics})

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
            raise ValueError("Provide topics or both abi, event_name")

        generated_topics = self._abi_filter.register_abi_filter(
            abi=abi, address=address, event_name=event_name
        )
        self.add_log_filter(address=address, topics=generated_topics)

    async def start(self) -> None:
        self._running = True
        delay = self.reconnect_delay
        self.logger.info("Starting WebSocketListener")

        while self._running:
            try:
                provider = WebSocketProvider(self.rpc_url)
                async with AsyncWeb3(provider) as w3:
                    if needs_poa_middleware(self.chain_id):
                        w3.middleware_onion.inject(
                            ExtraDataToPOAMiddleware, layer=0
                        )
                        self.logger.debug(
                            "Injected ExtraDataToPOAMiddleware, chain_id=%s",
                            self.chain_id,
                        )

                    self._w3 = w3
                    delay = self.reconnect_delay

                    self._reset_state()

                    self._block_fetcher = BlockFetcher(w3, self.logger)

                    sub_id = await w3.eth.subscribe("newHeads")
                    self._subscription_ids.append(str(sub_id))
                    self.logger.info(
                        "Subscribed to newHeads (sub_id=%s)", sub_id
                    )

                    for flt in self._log_filters:
                        filter_params: dict = {}
                        if flt["address"]:
                            filter_params["address"] = flt["address"]
                        if flt["topics"]:
                            filter_params["topics"] = flt["topics"]
                        log_sub_id = await w3.eth.subscribe(
                            "logs", filter_params
                        )
                        self._subscription_ids.append(str(log_sub_id))
                        self.logger.info(
                            "Subscribed to logs (sub_id=%s) filter=%s",
                            log_sub_id,
                            filter_params,
                        )

                    self._worker_task = asyncio.create_task(
                        self._block_worker()
                    )

                    async for message in w3.socket.process_subscriptions():
                        if not self._running:
                            break
                        try:
                            await self._process_message(message)
                        except Exception as exc:
                            self.logger.error(
                                "Message processing error: %s", exc
                            )
                            asyncio.create_task(
                                self._dispatcher.emit("error", exc)
                            )

            except Exception as exc:
                self.logger.error("Listener error: %s", exc)
                asyncio.create_task(self._dispatcher.emit("error", exc))
            finally:
                await self._cleanup()

            if self._running:
                self.logger.info("Reconnecting in %.1fs…", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def stop(self) -> None:
        self._running = False
        self.logger.info("Listener stop requested.")

    def _reset_state(self) -> None:
        while not self._header_queue.empty():
            try:
                self._header_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._subscription_ids.clear()
        self._block_processor.reset()

    async def _cleanup(self) -> None:
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None

        if self._w3 and self._subscription_ids:
            for sub_id in self._subscription_ids:
                try:
                    await self._w3.eth.unsubscribe(sub_id)
                except Exception:
                    pass

        self._w3 = None
        self._block_fetcher = None

    async def _block_worker(self) -> None:
        while self._running:
            try:
                header = await asyncio.wait_for(
                    self._header_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                block_hash = header.get("hash")
                if not block_hash:
                    continue

                if (
                    self.block_detail == BlockDetail.FULL_BLOCK
                    and self._block_fetcher
                ):
                    block = await self._block_fetcher.fetch_complete(
                        block_hash
                    )
                    if block:
                        await self._block_processor.process(
                            block, self._dispatcher.emit
                        )
                    else:
                        self.logger.error(
                            "Skipping block %s — could not fetch block.",
                            block_hash,
                        )
                else:
                    asyncio.create_task(self._dispatcher.emit("block", header))

            except Exception as exc:
                self.logger.error("Block worker error: %s", exc)
                asyncio.create_task(self._dispatcher.emit("error", exc))
            finally:
                self._header_queue.task_done()

    def _decode_log(self, log: dict) -> dict:
        return self._abi_filter.decode_log(log)

    async def _emit(self, event: str, payload: Any) -> None:
        await self._dispatcher.emit(event, payload)

    async def _process_message(self, message: dict) -> None:
        if "result" not in message:
            return
        result = message["result"]

        if not isinstance(result, AttributeDict):
            return

        if "number" in result:
            try:
                self._header_queue.put_nowait(result)
            except asyncio.QueueFull:
                self.logger.warning(
                    "Header queue full — dropping header for block %s. "
                    "Consider increasing _HEADER_QUEUE_MAX.",
                    result.get("number"),
                )

        elif "topics" in result and "data" in result:
            decoded_log = self._decode_log(result)
            asyncio.create_task(self._dispatcher.emit("log", decoded_log))
