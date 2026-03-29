"""
Example: Watch transactions via ChainSniper with Filter.

This script demonstrates how to monitor blockchain transactions using the
ChainSniper builder pattern with Filter for MongoDB-style rule matching.
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging


async def handle_error(error: Exception) -> None:
    """Handle listener errors."""
    logger.error("Listener error: %s", error)


async def main() -> None:
    """Main entry point."""
    # Setup logging
    global logger
    logger = setup_logging(level="INFO", logger_name="tx-watcher-dynamic")

    # Get RPC URL (supports both HTTP and WebSocket)
    rpc_url = get_rpc_url()
    logger.info("Connecting to: %s", rpc_url)

    # Create ChainSniper instance
    sniper = ChainSniper(rpc_url)

    # Configure to receive full blocks with transaction data
    sniper.block_detail("full_block")

    # Create Filter with transaction rules
    tx_filter = Filter()

    # Example 1: Filter transactions by recipient address
    tx_filter.add_tx_rule({
        "to": "0x55d398326f99059fF775485246999027B3197955"
    })

    # Example 2: Filter transactions with value >= 0.1 ETH (10^17 wei)
    # tx_filter.add_tx_rule({
    #     "value": {"_op": "$gte", "_value": 10**17}
    # })

    # Example 3: Filter transactions from specific addresses
    # tx_filter.add_tx_rule({
    #     "from": {
    #         "_op": "$in",
    #         "_value": [
    #             "0x1234567890abcdef1234567890abcdef12345678",
    #             "0xabcdef1234567890abcdef1234567890abcdef12",
    #         ]
    #     }
    # })

    # Example 4: Filter contract calls (transactions with input data)
    # tx_filter.add_tx_rule({
    #     "input": {"_op": "$ne", "_value": "0x"}
    # })

    # Example 5: Complex rule - high value transfers to specific address
    # tx_filter.add_tx_rule({
    #     "to": "0x55d398326f99059fF775485246999027B3197955",
    #     "value": {"_op": "$gte", "_value": 10**18}  # >= 1 ETH
    # })

    # Add filter to sniper
    sniper.filter(tx_filter)

    # Register error handler
    sniper.on_error(handle_error)

    logger.info(
        "Starting transaction watcher with Filter... (Ctrl+C to stop)"
    )
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
