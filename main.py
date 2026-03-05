import asyncio
import logging
import os


import dotenv

from listener.websocket_listener import WebSocketListener, BlockDetail
from engine.pipeline import Pipeline
from abstracts.base_filter import BaseFilter
from abstracts.base_strategy import BaseStrategy


dotenv.load_dotenv()
RPC_URL = os.getenv("RPC_URL")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class Filter(BaseFilter):
    def match(self, tx):
        return tx.get("to").lower() == "0x55d398326f99059fF775485246999027B3197955".lower()
    
    def match_log(self, log):
        # check the amount > 100 USDT (with 18 decimals)
        amount = int(log.get("data", "0x")[-64:], 16)
        return amount > 5000 * (10 ** 18)


class Strategy(BaseStrategy):
    async def execute(self, tx):
        logger.info(f"Executing strategy for transaction: {tx}")
        # Add your custom logic here
        # for example, save to database, send notification, etc.

    async def execute_log(self, log):
        print(f"Transection hash: {log.get('transactionHash')} Amount: {int(log.get('data', '0x')[-64:], 16) / (10 ** 18)} USDT")
        # Add your custom logic here
        # for example, save to database, send notification, etc.



async def main():

    pipeline = Pipeline(filter=Filter(), strategy=Strategy())

    listener = WebSocketListener(RPC_URL, block_detail=BlockDetail.FULL_BLOCK)



    # listener.on("block", pipeline.process_block)
    listener.add_log_filter(address="0x55d398326f99059fF775485246999027B3197955", topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"])
    listener.on("log", pipeline.process_log)

    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
