"""
Example: Decode transaction input data using ChainSniper with real listener.

This script demonstrates how to decode transaction input data using
the ChainSniper decode_input_data method with an ABI in a real listener.
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.utils.logging import setup_logging
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.parser.tx_parser import TransactionParser
from chain_sniper.utils.abis import load_abi_from_file

# Initialize logger and transaction parser
tx_parser = TransactionParser()

# Load ERC20 ABI for decoding input data
ERC20_ABI = load_abi_from_file("examples/abis/erc20.json")


async def handle_block_with_transactions(block: dict) -> None:
    """
    Process each new block and extract transactions with decoded input data.
    """
    if not block:
        logger.warning("Received empty block data")
        return

    try:
        block_number = block["number"]
        transactions = block.get("transactions", [])

        logger.info(
            "Block #%d | Transactions: %d",
            block_number,
            len(transactions),
        )

        # Process each transaction in the block
        for tx in transactions:
            # Skip if tx is just a hash string (header-only mode)
            if isinstance(tx, str):
                continue

            await process_transaction(tx, block_number)

    except Exception as e:
        logger.error(
            "Error processing block %s: %s",
            block.get("number", "unknown"),
            e,
            exc_info=True,
        )


async def process_transaction(tx: dict, block_number: int) -> None:
    """
    Process a single transaction with decoded input data.
    """
    from_addr = tx.get("from", "unknown")
    to_addr = tx.get("to")
    input_data = tx.get("input", "0x")

    function_name, decoded_args, error_message = tx_parser.decode_input(
        input_data, ERC20_ABI, to_addr
    )
    # if error_message:
    #     logger.warning(
    #         "From: %s | Decode error: %s",
    #         from_addr,
    #         error_message,
    #     )

    if function_name and function_name == "transfer":
        token_to = decoded_args.get("_to")
        token_value = decoded_args.get("_value", 0)
        token_value = token_value / (10 ** 18)  # Assuming 18 decimals

        logger.info(
            "Transfer detected | From: %s | To: %s | Value: %.4f USDT ",
            from_addr,
            token_to,
            token_value,
        )


async def handle_error(error: Exception) -> None:
    """Handle listener errors."""
    logger.error("Listener error: %s", error)


async def main() -> None:
    """Main entry point."""
    # Setup logging
    global logger
    logger = setup_logging(level="INFO", logger_name="decode-input-listener")

    # Get RPC URL (supports both HTTP and WebSocket)
    rpc_url = get_rpc_url()
    logger.info("Connecting to: %s", rpc_url)

    # Create ChainSniper instance
    sniper = ChainSniper(rpc_url)

    # Configure to receive full blocks with transaction data
    sniper.block_detail("full_block")

    # Create Filter with ABI for decoding input data
    tx_filter = Filter()
    tx_filter.add_tx_rule({
        "to": "0x55d398326f99059fF775485246999027B3197955"
        })

    # Add filter to sniper
    sniper.filter(tx_filter)

    # Register block handler
    sniper.on_block(handle_block_with_transactions)

    # Register error handler
    sniper.on_error(handle_error)

    logger.info("Starting transaction watcher with input data decoding...")
    # logger.info("Filter config: %s", tx_filter.get_config())

    # Start listening
    await sniper.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
