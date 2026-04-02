import logging
import json
import asyncio
import aiofiles
from eth_utils.conversions import to_hex
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging

logger = setup_logging(level="INFO", logger_name="tx-watcher")
logging.getLogger("web3").setLevel(logging.WARNING)

USE_FILTER = True

# queue for transactions
tx_queue: asyncio.Queue = asyncio.Queue()

OUTPUT_FILE = "transactions.jsonl"


# Writer Task
async def writer():
    """
    Dedicated async writer that saves transactions
    from the queue to disk efficiently.
    """
    async with aiofiles.open(OUTPUT_FILE, "a") as f:
        while True:
            tx = await tx_queue.get()
            tx_record = {
                "hash": to_hex(tx.get("hash", "?")),
                "from": tx.get("from", "?"),
                "to": tx.get("to") or "CONTRACT_CREATION",
                "value": tx.get("value", 0) / 10**18,  # convert to ETH
            }

            try:
                line = json.dumps(tx_record) + "\n"
                await f.write(line)
            except Exception as e:
                logger.error("Write error: %s", e)

            tx_queue.task_done()


# Transaction Handler
async def handle_transaction(tx: dict) -> None:
    """
    Handles each transaction event.
    Pushes transaction into async queue.
    """

    tx_hash = tx.get("hash", "?")
    from_addr = tx.get("from", "?")
    to_addr = tx.get("to") or "CONTRACT_CREATION"
    value_wei = tx.get("value", 0)
    value_eth = value_wei / 10**18
    block_num = tx.get("blockNumber", "?")

    await tx_queue.put(tx)

    logger.info(
        "Tx %s: %s -> %s | value: %.4f ETH | block: %s",
        to_hex(tx_hash),
        from_addr,
        to_addr,
        value_eth,
        block_num,
    )


async def handle_transaction_async_task(tx: dict):
    asyncio.create_task(handle_transaction(tx))


async def handle_error(error: Exception) -> None:
    logger.error("Listener error: %s", error)


# Main
async def main() -> None:

    rpc_url = get_rpc_url()
    logger.info("Connecting to: %s", rpc_url)

    # start writer
    asyncio.create_task(writer())

    sniper = (
        ChainSniper(rpc_url)
        .block_detail("full_block")
        .on_transaction(handle_transaction_async_task)
        .on_error(handle_error)
    )

    if USE_FILTER:
        f = Filter()
        f.add_tx_rule({"value": {"_op": "$gte", "_value": 10**17}})
        sniper.filter(f)

        logger.info("Filter active — rules: %s", f.get_config())
    else:
        logger.info("No filter — all transactions will be delivered")

    logger.info("Watching transactions... (Ctrl+C to stop)")
    await sniper.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
