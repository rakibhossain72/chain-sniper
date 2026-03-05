import asyncio
import logging
from typing import Any
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware
from listener.websocket_listener import WebSocketListener

# ==============================
# LOGGING SETUP
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("BNB-Watch")

# ==============================
# CONFIGURATION
# ==============================
RPC_HTTP = "https://bsc.drpc.org"
RPC_WS  = "wss://bsc.drpc.org"

TARGET_WALLET = AsyncWeb3.to_checksum_address("0x8894E0a0c962CB723c1976a4421c95949bE2D4E3")
MIN_AMOUNT_BNB = 0.1  # minimum amount to care about (in BNB)

# ==============================
# WEB3 CLIENT SETUP
# ==============================
w3 = AsyncWeb3(AsyncHTTPProvider(RPC_HTTP))
# BSC is PoA → needed for extraData handling
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# if not w3.is_connected():
#     logger.critical("Cannot connect to BSC RPC → exiting")
#     raise SystemExit(1)

async def handle_block(block_header: dict[str, Any]) -> None:
    """
    Called for every new block header.
    Looks for direct BNB transfers (value > 0) to the target wallet.
    """
    try:
        block_number = int(block_header["number"], 16)
        logger.debug("Processing block %d", block_number)

        block = await w3.eth.get_block(block_number, full_transactions=True)

        interesting_txs = 0

        for tx in block.transactions:
            if tx["to"] is None:
                continue  # contract creation — skip

            if tx["to"].lower() != TARGET_WALLET.lower():
                continue

            if tx["value"] == 0:
                continue  # no BNB sent

            amount_bnb = w3.from_wei(tx["value"], 'ether')

            if amount_bnb < MIN_AMOUNT_BNB:
                continue

            interesting_txs += 1

            print("═" * 70)
            print(f"Block       : {block_number:,d}")
            print(f"Tx Hash     : {tx['hash'].hex()}")
            print(f"From        : {tx['from']}")
            print(f"To (target) : {tx['to']}")
            print(f"Amount      : {amount_bnb:,.6f} BNB")
            print(f"Gas Price   : {w3.from_wei(tx['gasPrice'], 'gwei'):.2f} Gwei")
            print(f"Gas Limit   : {tx['gas']:,d}")
            print("═" * 70)

            logger.info(
                "Detected BNB inflow → %s BNB | tx: %s | from: %s",
                f"{amount_bnb:,.6f}",
                tx["hash"].hex(),
                tx["from"]
            )

        if interesting_txs == 0:
            logger.debug("Block %d → no interesting BNB transfers", block_number)

    except Exception as e:
        logger.error("Crashed while processing block %s → %s", block_number, e, exc_info=True)


async def main():
    logger.info("Starting BNB inflow monitor for wallet %s ...", TARGET_WALLET)
    logger.info("Minimum amount: ≥ %s BNB", MIN_AMOUNT_BNB)
    logger.info("Using RPC: %s (WS)", RPC_WS)

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
    except Exception as e:
        logger.critical("Main loop fatal error", exc_info=True)