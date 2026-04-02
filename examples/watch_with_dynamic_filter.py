"""
Example: Watch blockchain events with dynamic filtering via Redis.

This script demonstrates how to monitor blockchain transactions and events
using ChainSniper with dynamic filtering. Rules can be added, removed, and
cleared on a running listener via Redis Pub/Sub without restarting the bot.

Architecture:
    1. ChainSniper monitors blockchain events
    2. Filter applies rules to incoming transactions/events
    3. RedisRuleListener subscribes to Redis channel for new rules
    4. Rules are dynamically added/removed/cleared in real-time

Usage:
    # Terminal 1: Start the listener
    python examples/watch_with_dynamic_filter.py

    # Terminal 2: Push rules while listener is running
    python examples/push_redis_rule.py erc20
    python examples/push_redis_rule.py tx
    python examples/push_redis_rule.py batch

    # Terminal 2: Remove a specific rule by ID
    python examples/push_redis_rule.py remove <rule_id>

    # Terminal 2: Clear all tx or log rules
    python examples/push_redis_rule.py clear-tx
    python examples/push_redis_rule.py clear-log
    python examples/push_redis_rule.py clear-all

Requirements:
    - Redis server running on localhost:6379
    - RPC endpoint (HTTP or WebSocket)
"""

import asyncio
import logging
from typing import Any, Optional

from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.listener import RedisRuleListener
from chain_sniper.utils.abis import get_event_topic
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
# ==============================
# CONFIGURATION
# ==============================

# Redis configuration for dynamic rule pushing
REDIS_URL = "redis://localhost"
REDIS_CHANNEL = "sniper_rules"

# Enable/disable dynamic filtering via Redis
USE_DYNAMIC_FILTER = True

# Optional: Pre-load some rules at startup
PRELOAD_RULES = False

# Transfer event topic (keccak256 of "Transfer(address,address,uint256)")
TRANSFER_TOPIC = get_event_topic("Transfer(address,address,uint256)")

# Module-level reference for periodic filter state logging
_dynamic_filter: Optional[Filter] = None


def create_dynamic_filter() -> Filter:
    """
    Create and configure a Filter with optional pre-loaded rules.

    Returns:
        Configured Filter instance
    """
    dynamic_filter = Filter()

    if PRELOAD_RULES:
        # Example 1: Monitor USDT transfers
        dynamic_filter.add_log_rule(
            {
                "address": "0x55d398326f99059fF775485246999027B3197955",
                "target_topic": TRANSFER_TOPIC,
            }
        )

        # Example 2: Monitor transactions with value >= 0.1 ETH
        dynamic_filter.add_tx_rule({
            "value": {"_op": "$gte", "_value": 10**17}
        })

        logger.info(
            "Pre-loaded %d log rules and %d tx rules",
            len(dynamic_filter.log_rules),
            len(dynamic_filter.tx_rules),
        )

    return dynamic_filter


async def handle_block(block: dict[str, Any]) -> None:
    """
    Process each new block and extract transactions.

    When block_detail is set to "full_block", the block dict contains
    a "transactions" list with full transaction objects.
    """
    if not block:
        return

    try:
        block_number = block.get("number", "unknown")
        transactions = block.get("transactions", [])

        logger.info(
            "Block #%s | Transactions: %d",
            block_number,
            len(transactions),
        )

        # Log active rule count every 10 blocks for visibility
        if (
            isinstance(block_number, int) and
            block_number % 10 == 0 and _dynamic_filter
        ):
            config = _dynamic_filter.get_config()
            logger.info(
                "Filter state: %d tx rules, %d log rules",
                config["tx_rules_count"],
                config["log_rules_count"],
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


async def process_transaction(tx: dict[str, Any], block_number: Any) -> None:
    """
    Process a single transaction that passed the filter.

    Transaction dict contains:
        - hash: Transaction hash
        - from: Sender address
        - to: Recipient address (None for contract creation)
        - value: Value transferred in wei (hex string)
        - input: Transaction data (hex string)
    """
    tx_hash = tx.get("hash", "unknown")
    from_addr = tx.get("from", "unknown")
    to_addr = tx.get("to")
    value_wei = tx.get("value", 0)
    input_data = tx.get("input", "0x")

    # Convert hex value to int and then to ETH
    value_eth = value_wei / 10**18

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
        tx_hash[:10],
        tx_type,
        from_addr[:8] + "..." if from_addr != "unknown" else from_addr,
        (to_addr[:8] + "...") if to_addr else "NEW",
        value_eth,
    )


async def handle_log(event: dict[str, Any]) -> None:
    """
    Process log events that passed the filter.

    Log event dict contains:
        - address: Contract address
        - topics: List of topic hashes
        - data: Event data (hex string)
        - blockNumber: Block number
        - transactionHash: Transaction hash
    """
    address = event.get("address", "unknown")
    topics = event.get("topics", [])
    tx_hash = event.get("transactionHash", "unknown")
    block_number = event.get("blockNumber", "unknown")

    logger.info(
        "  LOG: %s | Block: %s | TX: %s | Topics: %d",
        address[:10],
        block_number,
        tx_hash[:10],
        len(topics),
    )


async def handle_error(error: Exception) -> None:
    """Handle listener errors."""
    logger.error("Listener error: %s", error)


async def start_redis_rule_listener(
    dynamic_filter: Filter,
) -> Optional[RedisRuleListener]:
    """
    Start the Redis rule listener for dynamic filtering.

    Args:
        dynamic_filter: Filter instance to add rules to

    Returns:
        RedisRuleListener instance or None if disabled
    """
    if not USE_DYNAMIC_FILTER:
        logger.info("Dynamic filtering via Redis is disabled")
        return None

    try:
        redis_listener = RedisRuleListener(
            dynamic_filter=dynamic_filter,
            redis_url=REDIS_URL,
            channel=REDIS_CHANNEL,
        )

        await redis_listener.start()
        logger.info(
            "Redis rule listener started on channel '%s'",
            REDIS_CHANNEL,
        )
        logger.info("Push rules using: examples/push_redis_rule.py [action]")

        return redis_listener

    except Exception as e:
        logger.error(
            "Failed to start Redis rule listener: %s\n"
            "Dynamic filtering will not be available.",
            e,
        )
        return None


async def main() -> None:
    """Main entry point."""
    # Setup logging
    global logger, _dynamic_filter
    logger = setup_logging(level="INFO", logger_name="dynamic-watcher")

    # Get RPC URL (supports both HTTP and WebSocket)
    rpc_url = get_rpc_url()
    logger.info("Connecting to: %s", rpc_url)

    # Create dynamic filter
    dynamic_filter = create_dynamic_filter()
    _dynamic_filter = dynamic_filter

    # Create ChainSniper instance
    sniper = ChainSniper(rpc_url)

    # Configure to receive full blocks with transaction data
    sniper.block_detail("full_block")

    # Apply the dynamic filter
    if USE_DYNAMIC_FILTER:
        sniper.filter(dynamic_filter)
        logger.info("Using dynamic filter with Redis rule listener")
    else:
        logger.info("Using static filtering (no Redis)")

    # Register block handler
    sniper.on_block(handle_block)

    # Register error handler
    sniper.on_error(handle_error)

    # Start Redis rule listener for dynamic filtering
    redis_listener = await start_redis_rule_listener(dynamic_filter)

    logger.info("Starting blockchain watcher... (Ctrl+C to stop)")
    logger.info("=" * 60)

    # Log initial filter state
    config = dynamic_filter.get_config()
    if config["has_dynamic_rules"]:
        logger.info(
            "Active rules: %d tx, %d log",
            config["tx_rules_count"],
            config["log_rules_count"],
        )
        for rid in config["tx_rule_ids"]:
            logger.info("  TX rule_id: %s", rid)
        for rid in config["log_rule_ids"]:
            logger.info("  Log rule_id: %s", rid)

    try:
        # Start listening
        await sniper.start()
    except KeyboardInterrupt:
        logger.warning("Received Ctrl+C → shutting down")
    except Exception as e:
        logger.critical("Listener crashed → %s", e, exc_info=True)
    finally:
        # Cleanup
        sniper.stop()

        if redis_listener:
            await redis_listener.stop()
            logger.info("Redis rule listener stopped")

        logger.info("Monitor stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        logger = logging.getLogger("dynamic-watcher")
        logger.critical("Fatal error: %s", e, exc_info=True)
