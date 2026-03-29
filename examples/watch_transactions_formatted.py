"""
Example: Watch transactions with human-readable formatting.

This script demonstrates how to monitor blockchain transactions using the
ChainSniper builder pattern with human-readable output formatting.
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.rpc_pool.rpc_pool import RPCPool
from chain_sniper.utils.logging import setup_logging
from chain_sniper.utils.format import format_transaction, print_transaction


async def handle_error(error: Exception) -> None:
    """Handle listener errors."""
    logger.error("Listener error: %s", error)


async def main() -> None:
    """Main entry point."""
    # Setup logging
    global logger
    logger = setup_logging(level="INFO", logger_name="tx-watcher-formatted")

    # Get RPC URL (supports both HTTP and WebSocket)
    BSC_RPCS = [
        "https://bsc-dataseed1.binance.org",
        "https://bsc-dataseed2.binance.org",
        "https://bsc-dataseed3.binance.org",
        "https://bsc-dataseed4.binance.org",
        "https://public-bsc-mainnet.fastnode.io",
    ]
    
    pool = await RPCPool.create(rpcs=BSC_RPCS, expected_chain_id=56)

    # Create ChainSniper instance
    sniper = ChainSniper(pool)

    # Configure to receive full blocks with transaction data
    sniper.block_detail("full_block")

    # Create Filter with transaction rules
    tx_filter = Filter()

    # Example: Filter transactions with value >= 0.01 ETH (10^16 wei)
    tx_filter.add_tx_rule({"value": {"_op": "$gte", "_value": 10**16}})

    # Add filter to sniper
    sniper.filter(tx_filter)

    # Register block handler with formatted output
    @sniper.on_block
    async def handle_block_with_transactions(block: dict) -> None:
        """Process each new block and extract transactions with formatting."""
        if not block:
            print("Received empty block data.")
            return

        try:
            block_number = int(block["number"], 16)
            transactions = block.get("transactions", [])

            logger.info("Block #%d | Transactions: %d", block_number, len(transactions))

            # Process each transaction in the block
            for tx in transactions:
                # Skip if tx is just a hash string (header-only mode)
                if isinstance(tx, str):
                    continue

                # Format transaction for human-readable output
                formatted_tx = format_transaction(tx, token_decimals=18)

                # Print formatted transaction
                print_transaction(formatted_tx, token_decimals=18, token_symbol="BNB")

        except Exception as e:
            logger.error("Error processing block: %s", e, exc_info=True)


    # Register error handler
    sniper.on_error(handle_error)

    logger.info("Starting transaction watcher with formatting... (Ctrl+C to stop)")
    if tx_filter.tx_rules:
        logger.info("Filter rules: %s", tx_filter.tx_rules)
    else:
        logger.info("Filter rules: None (showing all)")

    # Start listening
    await sniper.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
