import asyncio
import json
import logging
from typing import Callable, Awaitable, Any

import websockets
from websockets.exceptions import ConnectionClosed

from chain_sniper.listener.common import BlockDetail, _IdGen
from chain_sniper.utils.abi_filter import ABIFilterRegistry


class WebSocketListener:
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
        self._ws = None

        self._listeners: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "block": [],
            "log": [],
            "error": [],
        }
        self._log_filters: list[dict] = []
        self._sub_map: dict[str, str] = {}
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
                async with websockets.connect(self.rpc_url) as ws:
                    self._ws = ws
                    self._sub_map.clear()
                    delay = self.reconnect_delay

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

    async def _rpc(self, ws, method: str, params: list) -> Any:
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
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"RPC error: {msg['error']}")
                return msg["result"]
            await self._dispatch(msg)

    async def _subscribe_heads(self, ws) -> str:
        sub_id = await self._rpc(ws, "eth_subscribe", ["newHeads"])
        self._sub_map[sub_id] = "block"
        self.logger.info("Subscribed to newHeads  -> sub_id=%s", sub_id)
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
                "Subscribed to logs     -> sub_id=%s  filter=%s",
                sub_id,
                params,
            )

    async def _fetch_full_block(self, ws, block_hash: str) -> dict:
        return await self._rpc(ws, "eth_getBlockByHash", [block_hash, True])

    async def _dispatch(self, msg: dict) -> None:
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
                        result = await self._fetch_full_block(
                                self._ws, block_hash
                            )
                    except Exception as exc:
                        self.logger.warning(
                            "Could not fetch full block %s: %s",
                            block_hash,
                            exc,
                        )
            await self._emit("block", result)

        elif event == "log":
            await self._emit("log", self._decode_log(result))
