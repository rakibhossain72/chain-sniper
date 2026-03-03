import asyncio
import json
import websockets
from typing import Callable, Awaitable


class WebSocketListener:
    def __init__(self, rpc_url: str, on_block: Callable[[dict], Awaitable[None]]):
        self.rpc_url = rpc_url
        self.on_block = on_block
        self._id = 1
        self._running = False

    async def _subscribe(self, ws):
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": "eth_subscribe",
            "params": ["newHeads"],
        }
        await ws.send(json.dumps(payload))
        response = await ws.recv()
        data = json.loads(response)
        return data["result"]

    async def start(self):
        self._running = True

        while self._running:
            try:
                async with websockets.connect(self.rpc_url) as ws:
                    sub_id = await self._subscribe(ws)
                    print(f"Subscribed with ID: {sub_id}")

                    async for message in ws:
                        data = json.loads(message)

                        if "params" in data:
                            block_header = data["params"]["result"]
                            await self.on_block(block_header)

            except Exception as e:
                print(f"Listener error: {e}")
                print("Reconnecting in 3 seconds...")
                await asyncio.sleep(3)

    def stop(self):
        self._running = False