import asyncio
import logging
from typing import Callable, Awaitable, Any

from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider
from web3.datastructures import AttributeDict
from web3.middleware import ExtraDataToPOAMiddleware

from chain_sniper.listener.common import BlockDetail, needs_poa_middleware
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
    ) -> None:
        self.rpc_url = rpc_url
        self.block_detail = block_detail
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.chain_id = chain_id
        self.logger = logger or logging.getLogger("WebSocketListener")

        self._running = False
        self._w3: AsyncWeb3 | None = None

        self._listeners: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "block": [],
            "transaction": [],
            "log": [],
            "error": [],
        }
        self._log_filters: list[dict] = []
        self._abi_filter = ABIFilterRegistry()

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
                    # Inject POA middleware if the chain needs it
                    if needs_poa_middleware(self.chain_id):
                        w3.middleware_onion.inject(
                            ExtraDataToPOAMiddleware, layer=0
                        )
                        self.logger.debug(
                            "Injected ExtraDataToPOAMiddleware "
                            "for chain_id=%s",
                            self.chain_id
                        )
                    self._w3 = w3
                    delay = self.reconnect_delay

                    # Subscribe to new block headers
                    await w3.eth.subscribe("newHeads")
                    self.logger.info("Subscribed to newHeads")

                    # Subscribe to logs if filters are configured
                    for flt in self._log_filters:
                        filter_params = {}
                        if flt["address"]:
                            filter_params["address"] = flt["address"]
                        if flt["topics"]:
                            filter_params["topics"] = flt["topics"]

                        await w3.eth.subscribe("logs", filter_params)
                        self.logger.info(
                            "Subscribed to logs with filter: %s", filter_params
                        )

                    # Process incoming messages
                    async for message in w3.socket.process_subscriptions():
                        if not self._running:
                            break
                        try:
                            await self._process_message(message)
                        except Exception as exc:
                            self.logger.error(
                                "Message processing error: %s", exc
                                )
                            await self._emit("error", exc)

            except Exception as exc:
                self.logger.error("Listener error: %s", exc)
                await self._emit("error", exc)
            finally:
                self._w3 = None

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

    async def _process_message(self, message: dict) -> None:
        """Process incoming WebSocket message."""
        if "result" not in message:
            return
        result = message["result"]

        # Determine event type based on result structure
        if isinstance(result, AttributeDict):
            if "number" in result:
                # This is a block header
                if self.block_detail == BlockDetail.FULL_BLOCK and self._w3:
                    block_hash = result.get("hash")
                    if block_hash:
                        # --- RETRY LOGIC ADDED HERE ---
                        retries = 3
                        full_block = None

                        for attempt in range(retries):
                            try:
                                # Fetch full block with transactions
                                full_block = await self._w3.eth.get_block(
                                    block_hash, full_transactions=True
                                )
                                break  # Success! Break out of the retry loop
                            except Exception as exc:
                                if (
                                    "not found" in str(exc).lower()
                                    and attempt < retries - 1
                                ):
                                    self.logger.debug(
                                        "Block %s not found yet, retrying",
                                        (
                                            block_hash.hex()
                                            if isinstance(block_hash, bytes)
                                            else block_hash
                                        ),
                                    )
                                    await asyncio.sleep(0.5)
                                else:
                                    self.logger.warning(
                                        "Could not fetch full block %s after "
                                        "%s attempts: %s",
                                        block_hash,
                                        attempt + 1,
                                        exc,
                                    )

                        # emit if we actually successfully retrieved the block
                        if full_block:
                            await self._emit("block", full_block)
                            for tx in full_block.get("transactions", []):
                                await self._emit("transaction", tx)
                        else:
                            self.logger.error(
                                "Skipping block %s due to fetch failure.",
                                block_hash
                            )

                else:
                    # If we only need the header, emit it directly
                    await self._emit("block", result)

            elif "topics" in result and "data" in result:
                # This is a log
                await self._emit("log", self._decode_log(result))
