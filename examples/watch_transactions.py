"""
Example: Watch transactions via ChainSniper.

This script demonstrates how to monitor blockchain transactions using the
ChainSniper builder pattern with two filtering approaches:
1. Simple filtering (address and value thresholds)
2. DynamicFilter with MongoDB-style rule matching
"""

import asyncio
from typing import Any
from chain_sniper import ChainSniper
from chain_sniper.filters.dynamic_filter import DynamicFilter
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging

# ── Configuration ────────────────────────────────────────────────────────────
# Simple filtering: Filter transactions by specific addresses
WATCHED_ADDRESSES = {
    # "0xYourAddressHere",
    # "0xContractAddressHere",
}

# Simple filtering: Min value threshold (in wei) to filter small txs
MIN_VALUE_WEI = 0  # Set to e.g., 10**16 (0.01 ETH) to filter small txs

# Dynamic filtering: Enable or disable DynamicFilter
USE_DYNAMIC_FILTER = False  # Set to True to use DynamicFilter instead


async def handle_block_with_transactions(block: dict[str, Any]) -> None:
    """
    Process each new block and extract transactions.

    When block_detail is set to "full_block", the block dict contains
    a "transactions" list with full transaction objects.
    """
    # Handle None or empty blocks gracefully
    if not block:
        logger.warning("Received empty block data")
        return

    try:
        block_number = int(block["number"], 16)
        block_hash = block.get("hash", "unknown")
        transactions = block.get("transactions", [])

        logger.info(
            "Block #%d | Hash: %s | Transactions: %d",
            block_number,
            block_hash[:10] + "...",
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


async def process_transaction(tx: dict[str, Any], block_number: int) -> None:
    """
    Process a single transaction.

    Transaction dict contains:
        - hash: Transaction hash
        - from: Sender address
        - to: Recipient address (None for contract creation)
        - value: Value transferred in wei (hex string)
        - input: Transaction data (hex string)
        - gas: Gas limit (hex string)
        - gasPrice: Gas price in wei (hex string)
        - nonce: Sender's transaction count (hex string)
        - transactionIndex: Position in block (hex string)
    """
    tx_hash = tx.get("hash", "unknown")
    from_addr = tx.get("from", "unknown")
    to_addr = tx.get("to")  # None for contract creation
    value_hex = tx.get("value", "0x0")
    input_data = tx.get("input", "0x")

    # Convert hex value to int
    value_wei = int(value_hex, 16)
    value_eth = value_wei / 10**18

    # Apply simple filters (only if not using DynamicFilter)
    if not USE_DYNAMIC_FILTER:
        if WATCHED_ADDRESSES:
            addr_watched = (
                from_addr in WATCHED_ADDRESSES
                or to_addr in WATCHED_ADDRESSES
            )
            if not addr_watched:
                return

        if value_wei < MIN_VALUE_WEI:
            return

    # Determine transaction type
    if to_addr is None:
        tx_type = "Contract Creation"
    elif input_data and input_data != "0x":
        tx_type = "Contract Call"
    else:
        tx_type = "Transfer"

    # Log transaction details
    logger.info(
        "  TX: %s | %s | %s -> %s | %.6f ETH",
        tx_hash[:10] + "...",
        tx_type,
        from_addr[:8] + "..." if from_addr != "unknown" else from_addr,
        (to_addr[:8] + "...") if to_addr else "NEW",
        value_eth,
    )

    # Additional details for contract interactions
    if tx_type == "Contract Call":
        if len(input_data) > 10:
            input_preview = input_data[:10] + "..."
        else:
            input_preview = input_data
        logger.info("    Input data: %s", input_preview)


async def handle_error(error: Exception) -> None:
    """Handle listener errors."""
    logger.error("Listener error: %s", error)


def create_dynamic_filter() -> DynamicFilter:
    """
    Create and configure a DynamicFilter with example rules.

    Returns:
        Configured DynamicFilter instance
    """
    tx_filter = DynamicFilter()

    # Example 1: Filter transactions by recipient address
    # tx_filter.add_tx_rule({
    #     "to": "0x55d398326f99059fF775485246999027B3197955"
    # })

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

    return tx_filter


async def main() -> None:
    """Main entry point."""
    # Setup logging
    global logger
    logger = setup_logging(level="INFO", logger_name="tx-watcher")

    # Get RPC URL (supports both HTTP and WebSocket)
    rpc_url = get_rpc_url()
    logger.info("Connecting to: %s", rpc_url)

    # Create ChainSniper instance
    sniper = ChainSniper(rpc_url)

    # Configure to receive full blocks with transaction data
    sniper.block_detail("full_block")

    # Apply filtering strategy
    if USE_DYNAMIC_FILTER:
        # Use DynamicFilter for MongoDB-style rule matching
        tx_filter = create_dynamic_filter()
        sniper.filter(tx_filter)
        logger.info("Using DynamicFilter with rules: %s",
                    tx_filter.tx_rules if tx_filter.tx_rules else "None")
    else:
        # Use simple filtering (applied in process_transaction)
        logger.info("Using simple filtering")
        logger.info("Watched addresses: %s", WATCHED_ADDRESSES or "All")
        logger.info("Min value threshold: %.4f ETH", MIN_VALUE_WEI / 10**18)

    # Register block handler (transactions are inside blocks)
    sniper.on_block(handle_block_with_transactions)

    # Register error handler
    sniper.on_error(handle_error)

    logger.info("Starting transaction watcher... (Ctrl+C to stop)")

    # Start listening
    await sniper.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
