"""
Watch blocks and transactions with value-based filtering.

Only transactions with value >= 1 BNB are emitted.
Also monitors USDT Transfer events on the same connection.

Set RPC_URL=wss://... in your .env file before running.

    python examples/watch_transactions_with_filter.py
"""

import asyncio
from chain_sniper import ChainSniper, TransactionFilter, LogFilter
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging

ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

USDT = "0x55d398326f99059fF775485246999027B3197955"
ONE_BNB = 10**18


async def main():
    logger = setup_logging(level="INFO", logger_name="watch-txs")

    tx_filter = TransactionFilter()
    tx_filter.add_rule({"value": {"_op": "$gte", "_value": ONE_BNB}})

    log_filter = LogFilter()
    log_filter.subscribe(address=USDT, abi=ERC20_ABI, event_name="Transfer")

    sniper = ChainSniper(get_rpc_url())
    sniper.filter(tx_filter=tx_filter, log_filter=log_filter)

    @sniper.on_transaction
    async def on_tx(tx):
        value_bnb = tx.get("value", 0) / ONE_BNB
        logger.info(
            "TX  hash=%s  from=%s  to=%s  value=%.4f BNB",
            tx.get("hash", b"").hex(),
            tx.get("from"),
            tx.get("to"),
            value_bnb,
        )

    @sniper.on_event
    async def on_transfer(event):
        args = event.get("args", {})
        value = args.get("value", 0) / 10**18
        logger.info(
            "USDT Transfer  from=%s  to=%s  value=%.4f",
            args.get("from"),
            args.get("to"),
            value,
        )

    @sniper.on_error
    async def on_error(exc):
        logger.error("Listener error: %s", exc)

    logger.info("Watching transactions (>= 1 BNB) and USDT transfers...")
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
