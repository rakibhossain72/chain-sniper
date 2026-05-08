import asyncio
import trace
from chain_sniper import ChainSniper
from chain_sniper.utils.logging import setup_logging

RPC_WS = "ws://127.0.0.1:8545"


async def main():
    logger = setup_logging(level="INFO", logger_name="block_watcher")

    sniper = ChainSniper(RPC_WS)
    sniper.block_detail("full_block")

    @sniper.on_block
    async def on_new_block(block):
        transactions = block.transactions
        logger.info("New block: %s Transactions: %d", block.number, len(transactions))

    @sniper.on_reorg
    async def on_reorg(event):
        logger.warning("Reorg detected: %s", event)

    @sniper.on_error
    async def on_error(exc):
        logger.error("Error: %s", exc)

    logger.info("Listening with WebSocket endpoint: %s", RPC_WS)

    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
