import asyncio
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.engine.pipeline import Pipeline
from chain_sniper.abstracts.base_strategy import BaseStrategy
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper.parser.log_decoder import parse_log
from chain_sniper.parser.block_parser import parse_block

from chain_sniper.utils.abi_filter import ABIFilterRegistry
ERC20_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":false,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}]'

class CustomStrategy(BaseStrategy):
    def __init__(self, logger):
        self.logger = logger
        self.abi_registry = ABIFilterRegistry()
        self.abi_registry.register_abi_filter(abi=ERC20_ABI, address="0x55d398326f99059fF775485246999027B3197955")

    async def execute(self, tx):
        tx_hash = tx.get('hash', 'unknown')
        self.logger.info(f"[PIPELINE STRATEGY] TX Matches Filter: {tx_hash}")
        if tx.get("input") and tx["input"] != "0x":
            func_name, args = self.abi_registry.decode_transaction(tx)
            if func_name:
                self.logger.info(f"[PIPELINE STRATEGY] TX Call Decoded => Function: {func_name}, Args: {args}")
    async def execute_log(self, log):
        decoded = self.abi_registry.decode_log(log)
        self.logger.info(f"[PIPELINE STRATEGY] Log Matches Filter & Decoded => {decoded}")

async def main():
    logger = setup_logging(level="INFO", logger_name="pipeline-strategy")
    rpc_url = get_rpc_url()
    
    sniper = ChainSniper(rpc_url)
    sniper.block_detail("full_block")
    
    my_filter = Filter()
    my_filter.add_tx_rule({"value": {"_op": "$gte", "_value": 1e16}})
    my_filter.add_log_rule({"address": "0x55d398326f99059fF775485246999027B3197955"})
    
    my_strategy = CustomStrategy(logger)
    
    # Configure Pipeline
    pipeline = Pipeline(filter=my_filter, strategy=my_strategy)
    
    # Hook the pipeline instance's block parsing method up to sniper on_block.
    # Pipeline process_block itself applies `filter.match()` and `strategy.execute()`
    sniper.on_block(pipeline.process_block)

    # Note: Pipeline log logic
    sniper.on_event(pipeline.process_log)
    
    logger.info("Starting sniper with Pipeline Filter Strategy...")
    await sniper.start()

if __name__ == "__main__":
    asyncio.run(main())
