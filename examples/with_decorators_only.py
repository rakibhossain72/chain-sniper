
import asyncio
from chain_sniper import ChainSniper, TransactionFilter, LogFilter
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper.parser.log_decoder import parse_log
from chain_sniper.parser.block_parser import parse_block
from chain_sniper.utils.abi_filter import ABIFilterRegistry

ERC20_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":false,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}]'

abi_registry = ABIFilterRegistry()
abi_registry.register_abi_filter(abi=ERC20_ABI, address="0x55d398326f99059fF775485246999027B3197955")

async def main():    
    logger = setup_logging(level="INFO", logger_name="decorators-only")
    rpc_url = get_rpc_url()
    
    sniper = ChainSniper(rpc_url)
    
    # Initialize split filters
    tx_filter = TransactionFilter()
    log_filter = LogFilter()
    
    # Adding rules
    tx_filter.add_rule({"value": {"_op": "$gte", "_value": 1e16}})
    # For logs, we use subscribe if we want node-side filtering
    log_filter.subscribe(address="0x55d398326f99059fF775485246999027B3197955")
    
    sniper.filter(tx_filter=tx_filter, log_filter=log_filter)

    @sniper.on_block
    async def handle_block(block):
        parsed_txs = parse_block(block)
        logger.info(f"[DECORATOR] Block decoded => Number of txs: {len(parsed_txs)}")

    @sniper.on_transaction
    async def handle_tx(tx):
        tx_hash = tx.get("hash", "unknown")
        logger.info(f"[DECORATOR] Filtered TX: {tx_hash}")
        if tx.get("input") and tx["input"] != "0x":
            func_name, args = abi_registry.decode_transaction(tx)
            if func_name:
                logger.info(f"[DECORATOR] TX Call Decoded => Function: {func_name}, Args: {args}")

    @sniper.on_event
    async def handle_log(log):
        decoded_log = abi_registry.decode_log(log)
        logger.info(f"[DECORATOR] Filtered Log Decoded => {decoded_log}")

    logger.info("Starting sniper with decorators...")
    await sniper.start()

if __name__ == "__main__":
    asyncio.run(main())
