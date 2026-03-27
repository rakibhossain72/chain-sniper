import logging
import asyncio
import os
import dotenv
import json

from chain_sniper.listener.poll_listener import HttpListener, BlockDetail

dotenv.load_dotenv()
RPC_URL = os.getenv("RPC_URL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("example")


async def on_block(block: dict) -> None:
    """Trigger when block comes

    Args:
        block (dict): full block data from on-chain
    """
    tx_count = len(block.get("transactions", []))
    number = int(block["number"], 16)
    print(f"[BLOCK] #{number:,}  hash={block['hash'][:12]}…  txs={tx_count}")


async def on_log(log: dict) -> None:
    print(log)
    exit(0)
    addr = log.get("address", "???")
    # Check if log is decoded
    if "event" in log:
        # Decoded log
        event_name = log.get("event")
        args = log.get("args", {})
        print(f"[LOG] {addr[:8]}… → {event_name}: {args}")
    else:
        # Raw log
        topics = log.get("topics", [])
        first_topic = topics[0][:10] + "…" if topics else "no-topic"
        print(f"[LOG] {addr[:8]}… → {first_topic}")


async def on_error(exc: Exception) -> None:
    print(f"[ERROR] {type(exc).__name__}: {exc}")


async def main() -> None:
    # Use HttpListener for HTTP polling instead of WebSocket
    listener = HttpListener(
        RPC_URL,
        block_detail=BlockDetail.FULL_BLOCK,  # or .HEADER (not txs)
        logger=logger,
        poll_interval=2.0,  # Poll every 2 seconds
    )

    # ── USDT on BSC (mainnet) ───────────────────────────────────────
    USDT = "0x55d398326f99059fF775485246999027B3197955"

    # Load ERC20 ABI
    with open("examples/abis/erc20.json", "r") as f:
        erc20_abi = json.load(f)

    # Option 1: Add filter using ABI and event name - automatically decodes logs!
    listener.add_abi_log_filter(abi=erc20_abi, address=USDT, event_name="Transfer")

    # Option 2: Add filter using topic hash - returns raw logs
    # TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    # listener.add_abi_log_filter(address=USDT, topics=[TRANSFER_TOPIC])

    # ── Register async callbacks ─────────────────────────────────────
    listener.on("block", on_block)
    listener.on("log", on_log)
    listener.on("error", on_error)

    print("Starting HTTP polling listener... (Ctrl+C to stop)\n")

    try:
        await listener.start()
    except KeyboardInterrupt:
        print("\nStop requested.")
        listener.stop()
    except Exception as exc:
        print(f"Fatal error: {exc}")
        listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
