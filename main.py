
import json
import asyncio
from typing import Any

from eth_utils import address

from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper import ChainSniper, TransactionFilter, LogFilter
from chain_sniper.engine.pipeline import Pipeline
from chain_sniper.abstracts.base_strategy import BaseStrategy
from chain_sniper.utils.abis import get_event_topic

# Load configuration and setup logging
RPC_URL = "https://bsc-dataseed.bnbchain.org" #get_rpc_url()
logger = setup_logging(level="INFO", logger_name=__name__)

# Transfer event topic (keccak256 of "Transfer(address,address,uint256)")
TRANSFER_TOPIC = get_event_topic("Transfer(address,address,uint256)")
print(f"Transfer event topic: {TRANSFER_TOPIC}")

class Strategy(BaseStrategy):
    async def execute(self, tx: Any) -> None:
        value = tx.get("value", 0) / (10**18)
        print(f"Transaction hash: {tx.get('hash').hex()} Value: {value:.4f} BNB")

    async def execute_log(self, log):
        print(f"Log Address: {log}")

async def main():
    # 1. Initialize the split filters
    tx_filter = TransactionFilter()
    log_filter = LogFilter()

    # 2. Add an initial rule
    # log_filter.subscribe(address="0x55d398326f99059fF775485246999027B3197955", topics=[TRANSFER_TOPIC])

    # 3. Initialize pipeline with split filters
    pipeline = Pipeline(tx_filter=tx_filter, log_filter=log_filter, strategy=Strategy())

    # Create ChainSniper listener
    listener = ChainSniper(RPC_URL)
    
    # Register filters on the sniper
    listener.filter(tx_filter=tx_filter, log_filter=log_filter)

    listener.on_event(pipeline.process_log)
    
    # counter = 0
    # @listener.event(
    #     contract="0x55d398326f99059fF775485246999027B3197955",
    #     topics=[TRANSFER_TOPIC]
    # )
    # async def process_log(log):
    #     nonlocal counter
    #     counter += 1
    #     event, from_address, to_address = log.topics
    #     value_hex = log.data.hex()
    #     print(f"Log {counter} From: 0x{from_address.hex()[24:]}, Value: {int(value_hex, 16) / (10**18):.4f} USD")
        

    await listener.start()

if __name__ == "__main__":
    asyncio.run(main())
