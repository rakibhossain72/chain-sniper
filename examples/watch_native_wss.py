import asyncio
import logging
from typing import Any
from chain_sniper.listener import WebSocketListener

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
RPC_WS = "wss://bsc.drpc.org"

TARGET_WALLET = "0x8894E0a0c962CB723c1976a4421c95949bE2D4E3"
MIN_AMOUNT_BNB = 0.1  # minimum amount to care about (in BNB)


async def handle_block(block_header: dict[str, Any]) -> None:
    """
    Called for every new block header.
    Looks for direct BNB transfers (value > 0) to the target wallet.
    """
    try:
        # Block number is now an int (from web3py)
        block_number = block_header["number"]
        logger.debug("Processing block %d", block_number)

        # Block data is already formatted by web3py
        # Transactions are included if block_detail=BlockDetail.FULL_BLOCK
        if "transactions" not in block_header:
            logger.debug(
                "Block %d → no transactions (header only)",
                block_number
            )
            return

        interesting_txs = 0

        for tx in block_header["transactions"]:
            if tx["to"] is None:
                continue  # contract creation — skip

            if tx["to"].lower() != TARGET_WALLET.lower():
                continue

            if tx["value"] == 0:
                continue  # no BNB sent

            # Value is already an int (in wei) from web3py
            amount_bnb = tx["value"] / 10**18

            if amount_bnb < MIN_AMOUNT_BNB:
                continue

            interesting_txs += 1

            print("═" * 70)
            print(f"Block       : {block_number:,d}")
            print(f"Tx Hash     : {tx['hash'].hex()}")
            print(f"From        : {tx['from']}")
            print(f"To (target) : {tx['to']}")
            print(f"Amount      : {amount_bnb:,.6f} BNB")
            print(f"Gas Price   : {tx['gasPrice'] / 10**9:.2f} Gwei")
            print(f"Gas Limit   : {tx['gas']:,d}")
            print("═" * 70)

            logger.info(
                "Detected BNB inflow → %s BNB | tx: %s | from: %s",
                f"{amount_bnb:,.6f}",
                tx["hash"].hex(),
                tx["from"]
            )

        if interesting_txs == 0:
            logger.debug(
                "Block %d → no interesting BNB transfers",
                block_number
            )

    except Exception as e:
        logger.error(
            "Crashed while processing block %s → %s",
            block_number, e, exc_info=True
        )


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
    except Exception:
        logger.critical("Main loop fatal error", exc_info=True)
