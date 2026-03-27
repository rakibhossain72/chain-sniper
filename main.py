import asyncio
from typing import Any

from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper.utils.runner import create_websocket_listener
from chain_sniper.engine.pipeline import Pipeline
from chain_sniper.filters.dynamic_filter import DynamicFilter
from chain_sniper.listener.redis_rule_listener import RedisRuleListener
from chain_sniper.abstracts.base_strategy import BaseStrategy


# Load configuration and setup logging
RPC_URL = get_rpc_url()
logger = setup_logging(level="INFO", logger_name=__name__)


class Strategy(BaseStrategy):
    async def execute(self, data: Any) -> None:
        logger.info(f"Executing strategy for transaction: {data}")
        # Add your custom logic here
        # for example, save to database, send notification, etc.

    async def execute_log(self, log):
        # Check if decoded
        if "event" in log and log["event"] == "Transfer":
            args = log.get("args", {})
            amount = args.get("value", 0) / (10**18)
            print(
                f"Transfer: {args.get('from')} → {args.get('to')} Amount: {amount} USDT"
            )
        else:
            # Raw log
            amount = int(log.get("data", "0x")[-64:], 16) / (10**18)
            print(
                f"Transaction hash: {log.get('transactionHash')} Amount: {amount} USDT"
            )
        # Add your custom logic here
        # for example, save to database, send notification, etc.


async def main():
    # 1. Initialize the dynamic filter
    dyn_filter = DynamicFilter()

    # 2. Add an initial rule (optional)
    # dyn_filter.add_log_rule({"type": "log", "min_amount": 5000})

    # 3. Initialize pipeline with dynamic filter
    pipeline = Pipeline(filter=dyn_filter, strategy=Strategy())

    # Create WebSocket listener using utility function
    listener = create_websocket_listener(
        rpc_url=RPC_URL,
        block_detail="full_block",
        logger=logger,
    )

    # 4. Initialize Background Rule Listener (Redis)
    rule_listener = RedisRuleListener(dynamic_filter=dyn_filter)

    # Start the rule listener in the background
    await rule_listener.start()

    listener.on("block", pipeline.process_block)

    # Example: Add ABI-based log filter (much easier than topic hashes!)
    # import json
    # with open("examples/abis/erc20.json", "r") as f:
    #     erc20_abi = json.load(f)
    # listener.add_abi_log_filter(abi=erc20_abi, address="0x55d398326f99059fF775485246999027B3197955", event_name="Transfer")
    # listener.on("log", pipeline.process_log)

    # listener.on("log", pipeline.process_log)

    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
