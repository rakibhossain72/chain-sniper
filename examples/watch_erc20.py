import asyncio
import logging
from listener.websocket_listener import WebSocketListener, BlockDetail

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("example")

async def on_block(block: dict) -> None:
    tx_count = len(block.get("transactions", []))
    number = int(block["number"], 16)
    print(
        f"[BLOCK] #{number:,}  "
        f"hash={block['hash'][:12]}…  "
        f"txs={tx_count}"
    )

async def on_log(log: dict) -> None:
    addr = log.get("address", "???")
    topics = log.get("topics", [])
    first_topic = topics[0][:10] + "…" if topics else "no-topic"
    print(f"[LOG] {addr[:8]}… → {first_topic}")

async def on_error(exc: Exception) -> None:
    print(f"[ERROR] {type(exc).__name__}: {exc}")

async def main() -> None:
    # ── Use a public / your own BSC WebSocket endpoint ──
    RPC_URL = "wss://bsc.drpc.org"           # frequently DOES NOT support logs subscription
    # Better (paid): QuickNode/Alchemy/Chainstack/etc.

    listener = WebSocketListener(
        RPC_URL,
        block_detail=BlockDetail.FULL_BLOCK,   # or .HEADER if you don't need txs
        logger=logger,
    )

    # ── USDT on BSC (mainnet) ───────────────────────────────────────
    USDT = "0x55d398326f99059fF775485246999027B3197955"
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    listener.add_log_filter(
        address=USDT,
        topics=[TRANSFER_TOPIC],          # single topic = Transfer event
    )

    # ── Register async callbacks ─────────────────────────────────────
    listener.on("block", on_block)
    listener.on("log",   on_log)
    listener.on("error", on_error)

    print("Starting WebSocket listener... (Ctrl+C to stop)\n")

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