import asyncio
import dotenv
import os
from web3 import AsyncWeb3
from web3.providers.persistent import WebSocketProvider

dotenv.load_dotenv()
WSS_RPC = os.getenv("RPC_URL")

transfer_event_abi = {
    "anonymous": False,
    "inputs": [
        {"indexed": True,  "name": "from",  "type": "address"},
        {"indexed": True,  "name": "to",    "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"},
    ],
    "name": "Transfer",
    "type": "event",
}

USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"


async def main() -> None:
    async with AsyncWeb3(WebSocketProvider(WSS_RPC)) as w3:
        contract_address = AsyncWeb3.to_checksum_address(USDT_ADDRESS)
        contract = w3.eth.contract(
            address=contract_address,
            abi=[transfer_event_abi]
        )

        event = contract.events.Transfer()
        print(event._get_event_filter_params(event.abi))
        exit(0)
        filter_params = {
            "address": contract_address,
            "topics": event._get_event_filter_params(event.abi)["topics"],
        }

        subscription_id = await w3.eth.subscribe("logs", filter_params)
        print(f"Subscribed with ID: {subscription_id}")

        async for payload in w3.socket.process_subscriptions():
            try:
                log = payload["result"]
                decoded = contract.events.Transfer().process_log(log)
                print("FROM: ", decoded["args"]["from"])
                print("TO:   ", decoded["args"]["to"])
                print("VALUE:", decoded["args"]["value"])
                print("TX:   ", decoded["transactionHash"].hex())
                print()
            except Exception as e:
                print("Decode error:", e)

asyncio.run(main())
