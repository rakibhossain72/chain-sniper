import asyncio
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.listener.redis_rule_listener import RedisRuleListener
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper.parser.log_decoder import parse_log
from chain_sniper.parser.block_parser import parse_block
from chain_sniper.utils import load_abi_from_file

from chain_sniper.utils.abi_filter import ABIFilterRegistry
ERC20_ABI = load_abi_from_file("examples/abis/erc20.json")

abi_registry = ABIFilterRegistry()
abi_registry.register_abi_filter(abi=ERC20_ABI, address="0x55d398326f99059fF775485246999027B3197955")

async def handle_block(block):
    parsed_txs = parse_block(block)
    logger.info(f"[REDIS DYNAMIC] Block decoded. Contains {len(parsed_txs)} transactions.")
    
async def handle_tx(tx):
    tx_hash = tx.get("hash", "unknown")
    logger.info(f"[REDIS DYNAMIC] Filtered TX: {tx_hash}")
    # decode smart contract call
    if tx.get("input") and tx["input"] != "0x":
        func_name, args = abi_registry.decode_transaction(tx)
        if func_name:
            logger.info(f"[REDIS DYNAMIC] TX Call Decoded => Function: {func_name}, Args: {args}")

async def handle_log(log):
    decoded = abi_registry.decode_log(log)
    logger.info(f"[REDIS DYNAMIC] Filtered Log Decoded => {decoded}")
    
async def main():
    global logger
    logger = setup_logging(level="INFO", logger_name="redis-dynamic")
    rpc_url = get_rpc_url()
    
    sniper = ChainSniper(rpc_url)
    sniper.block_detail("full_block")
    
    dynamic_filter = Filter()
    
    # Adding default filters (can be modified via Redis)
    dynamic_filter.add_tx_rule({"value": {"_op": "$gte", "_value": 1e16}})
    dynamic_filter.add_log_rule({"address": "0x55d398326f99059fF775485246999027B3197955"})
    
    sniper.filter(dynamic_filter)
    
    sniper.on_block(handle_block)
    sniper.on_transaction(handle_tx)
    sniper.on_event(handle_log)
    
    # Needs valid redis_url to bind
    # Note: ensure redis server is up
    redis_listener = RedisRuleListener(dynamic_filter=dynamic_filter, redis_url="redis://localhost", channel="sniper_rules")
    await redis_listener.start()
    
    logger.info("Starting sniper with RedisRuleListener...")
    try:
        await sniper.start()
    finally:
        await redis_listener.stop()

if __name__ == "__main__":
    asyncio.run(main())
