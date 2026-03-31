"""
Example: Watch native token transfers via WebSocket (WSS).

This script demonstrates how to monitor native token (BNB/ETH) transfers
using WebSocket connection with various filtering checks:
- Minimum transfer value threshold
- Optional address watching (from/to)
- Transaction type filtering (transfers only, not contract calls)
- Formatted output with transfer details
"""

import asyncio
from typing import Any
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging

# ── Configuration ────────────────────────────────────────────────────────────

# Minimum transfer value in wei (0.01 BNB/ETH)
MIN_VALUE_WEI = 10**16

# Optional: Watch specific addresses (leave empty to watch all)
WATCHED_ADDRESSES = {
    # "0xYourAddressHere",
    # "0xContractAddressHere",
}

# Only show transfers (exclude contract calls)
TRANSFERS_ONLY = True

# Maximum number of transactions to display per block (0 = unlimited)
MAX_TX_PER_BLOCK = 10


async def handle_block_with_transfers(block: dict[str, Any]) -> None:
    """
    Process each new block and extract native token transfers.

    When block_detail is set to "full_block", the block dict contains
    a "transactions" list with full transaction objects.
    """
    if not block:
        logger.warning("Received empty block data")
        return

    try:
        # Block number is now an int (from web3py)
        block_number = block["number"]
        block_hash = block.get("hash", "unknown")
        transactions = block.get("transactions", [])

        logger.info(
            "Block #%d | Hash: %s | Transactions: %d",
            block_number,
            (
                block_hash[:10] + "..."
                if isinstance(block_hash, str)
                else block_hash.hex()[:10] + "..."
            ),
            len(transactions),
        )

        # Process each transaction in the block
        transfer_count = 0
        for tx in transactions:
            # Skip if tx is just a hash string (header-only mode)
            if isinstance(tx, str):
                continue

            # Check max transactions per block limit
            if MAX_TX_PER_BLOCK > 0 and transfer_count >= MAX_TX_PER_BLOCK:
                logger.info(
                    "  ... (showing first %d transfers)",
                    MAX_TX_PER_BLOCK,
                )
                break

            # Process transaction and check if it's a transfer
            is_transfer = await process_transaction(tx, block_number)
            if is_transfer:
                transfer_count += 1

        if transfer_count > 0:
            logger.info("  Found %d native transfers in block", transfer_count)

    except Exception as e:
        logger.error(
            "Error processing block %s: %s",
            block.get("number", "unknown"),
            e,
            exc_info=True,
        )


async def process_transaction(tx: dict[str, Any], block_number: int) -> bool:
    """
    Process a single transaction and check if it's a native transfer.

    Returns:
        True if transaction is a native transfer that passes filters,
        False otherwise.

    Transaction dict contains:
        - hash: Transaction hash
        - from: Sender address
        - to: Recipient address (None for contract creation)
        - value: Value transferred in wei (int from web3py)
        - input: Transaction data (hex string)
        - gas: Gas limit (int)
        - gasPrice: Gas price in wei (int)
        - nonce: Sender's transaction count (int)
        - transactionIndex: Position in block (int)
    """
    tx_hash = tx.get("hash")
    from_addr = tx.get("from", "unknown")
    to_addr = tx.get("to")  # None for contract creation
    value_wei = tx.get("value", 0)
    input_data = tx.get("input", "0x")

    # Convert hash to hex string if needed
    if hasattr(tx_hash, "hex"):
        tx_hash_hex = tx_hash.hex()
    else:
        tx_hash_hex = str(tx_hash)

    # Check if this is a transfer (no input data or empty input)
    is_transfer = (
        to_addr is not None
        and (not input_data or input_data == "0x")
    )

    # Skip if we only want transfers and this is not one
    if TRANSFERS_ONLY and not is_transfer:
        return False

    # Skip contract creation (to_addr is None)
    if to_addr is None:
        return False

    # Apply value filter
    if value_wei < MIN_VALUE_WEI:
        return False

    # Apply address filter if configured
    if WATCHED_ADDRESSES:
        addr_watched = (
            from_addr in WATCHED_ADDRESSES or to_addr in WATCHED_ADDRESSES
        )
        if not addr_watched:
            return False

    # Convert wei to BNB/ETH for display
    value_eth = value_wei / 10**18

    # Get gas price in Gwei
    gas_price_wei = tx.get("gasPrice", 0)
    gas_price_gwei = gas_price_wei / 10**9

    # Log transfer details
    logger.info(
        "  Transfer: %s → %s | %.6f BNB | Gas: %.2f Gwei",
        from_addr[:10] + "..." if len(from_addr) > 10 else from_addr,
        to_addr[:10] + "..." if len(to_addr) > 10 else to_addr,
        value_eth,
        gas_price_gwei,
    )
    logger.info(
        "    TX: %s | Block: %d",
        tx_hash_hex[:16] + "...",
        block_number,
    )

    return True


async def handle_error(error: Exception) -> None:
    """Handle listener errors."""
    logger.error("Listener error: %s", error)


def create_filter() -> Filter:
    """
    Create and configure a Filter with example rules.

    Returns:
        Configured Filter instance
    """
    tx_filter = Filter()

    # Example 1: Filter transactions with value >= 0.01 BNB (10^16 wei)
    # tx_filter.add_tx_rule({
    #     "value": {"_op": "$gte", "_value": 10**16}
    # })

    # Example 2: Filter transactions from specific addresses
    # tx_filter.add_tx_rule({
    #     "from": {
    #         "_op": "$in",
    #         "_value": [
    #             "0x1234567890abcdef1234567890abcdef12345678",
    #             "0xabcdef1234567890abcdef1234567890abcdef12",
    #         ]
    #     }
    # })

    # Example 3: Filter transactions to specific address with minimum value
    # tx_filter.add_tx_rule({
    #     "to": "0x55d398326f99059fF775485246999027B3197955",
    #     "value": {"_op": "$gte", "_value": 10**17}  # >= 0.1 BNB
    # })

    return tx_filter


async def main() -> None:
    """Main entry point."""
    # Setup logging
    global logger
    logger = setup_logging(level="INFO", logger_name="native-wss-watcher")

    # Get RPC URL (WebSocket)
    rpc_url = get_rpc_url()
    logger.info("Connecting to: %s", rpc_url)

    # Create ChainSniper instance
    sniper = ChainSniper(rpc_url, chain_id=56)  # BSC chain ID

    # Configure to receive full blocks with transaction data
    sniper.block_detail("full_block")

    # Optional: Use Filter for MongoDB-style rule matching
    # Uncomment to enable dynamic filtering
    # tx_filter = create_filter()
    # sniper.filter(tx_filter)
    # logger.info("Using Filter with rules: %s", tx_filter.tx_rules)

    # Register block handler (transactions are inside blocks)
    sniper.on_block(handle_block_with_transfers)

    # Register error handler
    sniper.on_error(handle_error)

    # Log configuration
    logger.info("Configuration:")
    logger.info("  Min value: %.4f BNB", MIN_VALUE_WEI / 10**18)
    logger.info("  Watched addresses: %s", WATCHED_ADDRESSES or "All")
    logger.info("  Transfers only: %s", TRANSFERS_ONLY)
    logger.info("  Max TX per block: %s", MAX_TX_PER_BLOCK or "Unlimited")

    logger.info("Starting native token transfer watcher... (Ctrl+C to stop)")

    # Start listening
    await sniper.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
