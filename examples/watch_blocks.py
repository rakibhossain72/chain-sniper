import asyncio
import logging
from typing import Any
from chain_sniper.listener import WebSocketListener

# LOGGING SETUP
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BNB-Watch")

# CONFIGURATION
RPC_WS = "wss://bsc.drpc.org"


async def handle_block(block_header: dict[str, Any]) -> None:
    """
    Called for every new block header.
    """
    try:
        block_number = int(block_header["number"], 16)
        logger.info("New block: %d", block_number)
    except Exception as e:
        logger.error(
            "Crashed at block %s → %s", block_number, e, exc_info=True
        )


async def main() -> None:
    try:
        listener = WebSocketListener(RPC_WS)
        listener.on("block", handle_block)
        await listener.start()

    except KeyboardInterrupt:
        logger.warning("Received Ctrl+C → shutting down")

    except Exception as e:
        logger.critical("Listener crashed → %s", e, exc_info=True)

    finally:
        logger.info("Monitor stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception:
        logger.critical("Main loop fatal error", exc_info=True)
