
import asyncio
from chain_sniper import ChainSniper, TransactionFilter, LogFilter
from chain_sniper.listener.redis_rule_listener import RedisRuleListener
from chain_sniper.utils.abis import get_event_topic
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper.parser.block_parser import parse_block
from chain_sniper.utils import load_abi_from_file
from chain_sniper.utils.abi_filter import ABIFilterRegistry



ERC20_ABI = load_abi_from_file("examples/abis/erc20.json")

USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
PANCAKE_VAULT = "0x238a358808379702088667322f80aC48bAd5e6c4"

abi_registry = ABIFilterRegistry()
abi_registry.register_abi_filter(abi=ERC20_ABI, address=USDT_ADDRESS)

TRANSFER_TOPIC = get_event_topic("Transfer(address,address,uint256)")

async def handle_block(block):
    parsed_txs = parse_block(block)
    logger.info(f"[REDIS DYNAMIC] Block decoded. Contains {len(parsed_txs)} transactions.")
    
async def handle_tx(tx):
    tx_hash = "0x" + tx.get("hash", "unknown").hex()
    logger.info(f"[REDIS DYNAMIC] Filtered TX: {tx_hash}")
    # decode smart contract call
    if tx.get("input") and tx["input"] != "0x":
        func_name, args = abi_registry.decode_transaction(tx)
        if func_name:
            logger.info(f"[REDIS DYNAMIC] TX Call Decoded => Function: {func_name}, Args: {args}")

async def handle_log(log):
    decoded = abi_registry.decode_log(log)
    to_address = decoded.get("args", {}).get("to")
    from_address = decoded.get("args", {}).get("from")
    value = decoded.get("args", {}).get("value")
    transaction_hash = log.get("transactionHash", "unknown").hex()
    if to_address == PANCAKE_VAULT:
        logger.info(f"[REDIS DYNAMIC] Log => Hash: {transaction_hash}, Value: {value / (10**18):.4f} USDT")
    
async def main():
    global logger
    logger = setup_logging(level="INFO", logger_name="redis-dynamic")
    rpc_url = get_rpc_url()
    
    sniper = ChainSniper(rpc_url)
    sniper.block_detail("full_block")
    
    # Initialize split filters
    tx_filter = TransactionFilter()
    log_filter = LogFilter()
    
    # Adding default filters (can be modified via Redis)
    tx_filter.add_rule({"value": {"_op": "$gte", "_value": 1e16}})
    # For node-side logs we subscribe
    log_filter.subscribe(address=USDT_ADDRESS, abi=ERC20_ABI, event_name="Transfer")
    # log_filter.subscribe(address=USDT_ADDRESS, topics=[TRANSFER_TOPIC])
    
    
    sniper.filter(tx_filter=tx_filter, log_filter=log_filter)
    
    sniper.on_block(handle_block)
    sniper.on_transaction(handle_tx)
    sniper.on_event(handle_log)
    
    # Use split filters for RedisRuleListener
    redis_listener = RedisRuleListener(
        tx_filter=tx_filter, 
        log_filter=log_filter, 
        redis_url="redis://localhost", 
        channel="sniper_rules"
    )
    await redis_listener.start()
    
    logger.info("Starting sniper with RedisRuleListener and split filters...")
    try:
        await sniper.start()
    finally:
        await redis_listener.stop()

if __name__ == "__main__":
    asyncio.run(main())
