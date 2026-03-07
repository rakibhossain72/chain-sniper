import asyncio
import logging
import os


import dotenv

from chain_sniper.listener.websocket_listener import WebSocketListener, BlockDetail
from chain_sniper.engine.pipeline import Pipeline
from chain_sniper.filters.dynamic_filter import DynamicFilter
from chain_sniper.listener.redis_rule_listener import RedisRuleListener
from chain_sniper.abstracts.base_strategy import BaseStrategy


dotenv.load_dotenv()
RPC_URL = os.getenv("RPC_URL")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)



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

    # 1. Initialize the dynamic filter
    dyn_filter = DynamicFilter()
    
    # 2. Add an initial rule (optional)
    # dyn_filter.add_log_rule({"type": "log", "min_amount": 5000})

    # 3. Initialize pipeline with dynamic filter
    pipeline = Pipeline(filter=dyn_filter, strategy=Strategy())

    listener = WebSocketListener(RPC_URL, block_detail=BlockDetail.FULL_BLOCK)
    
    # 4. Initialize Background Rule Listener (Redis)
    rule_listener = RedisRuleListener(dynamic_filter=dyn_filter)

    # Start the rule listener in the background
    await rule_listener.start()


    listener.on("block", pipeline.process_block)
    # listener.add_log_filter(address="0x55d398326f99059fF775485246999027B3197955", topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"])
    # listener.on("log", pipeline.process_log)

    # listener.on("log", pipeline.process_log)

    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
