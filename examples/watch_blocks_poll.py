import asyncio
import logging
from typing import Any
from chain_sniper.listener import HttpListener, BlockDetail

# ==============================
# LOGGING SETUP
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BNB-Watch")

# ==============================
# CONFIGURATION
# ==============================
RPC_HTTP = "https://bsc-dataseed.binance.org/"  # needs HTTP, not WS


async def main():
    listener = HttpListener(
        RPC_HTTP,
        block_detail=BlockDetail.FULL_BLOCK,
        poll_interval=3.0,
        chain_id=56,
    )

    async def handle_block(block_header: dict[str, Any]) -> None:
        try:
            # Block number is now an int (from web3py)
            block_number = block_header["number"]
            logger.info("New block: %d", block_number)
        except Exception as e:
            logger.error(
                "Crashed while processing block → %s", e, exc_info=True
            )

    async def handle_error(exc: Exception) -> None:
        logger.error("Listener error → %s", exc)

    listener.on("block", handle_block)
    listener.on("error", handle_error)

    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.warning("Received Ctrl+C → shutting down")
    except Exception as e:
        logger.critical("Listener crashed → %s", e, exc_info=True)
    finally:
        listener.stop()
        logger.info("Monitor stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception:
        logger.critical("Main loop fatal error", exc_info=True)
