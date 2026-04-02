"""
Example script for pushing dynamic rules to chain-sniper via Redis Pub/Sub.

This script demonstrates how to dynamically add, remove, and clear filtering
rules in a running chain-sniper instance without restarting the bot. Rules are
published to a Redis channel and consumed by the RedisRuleListener
in real-time.

Usage:
    python examples/push_redis_rule.py [action]

Actions:
    log         - Push a log event filter rule
    tx          - Push a transaction filter rule
    erc20       - Push an ERC20 transfer monitor rule
    nft         - Push an NFT transfer monitor rule
    batch       - Push multiple rules at once
    custom      - Push a custom rule with user-defined parameters
    remove      - Remove a rule by its rule_id
    clear-tx    - Clear all transaction rules
    clear-log   - Clear all log rules
    clear-all   - Clear all rules (tx and log)

Examples:
    # Monitor USDT transfers
    python examples/push_redis_rule.py erc20

    # Monitor transactions with value < 1 ETH
    python examples/push_redis_rule.py tx

    # Push multiple rules at once
    python examples/push_redis_rule.py batch

    # Remove a specific rule by ID
    python examples/push_redis_rule.py remove <rule_id>

    # Clear all transaction rules
    python examples/push_redis_rule.py clear-tx
"""

import json
import redis
import sys
from typing import Dict, Any

from chain_sniper.utils.abis import get_event_topic

# Transfer event topic (keccak256 of "Transfer(address,address,uint256)")
TRANSFER_TOPIC = get_event_topic("Transfer(address,address,uint256)")


def publish_message(
    payload: Dict[str, Any],
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    channel: str = "sniper_rules",
) -> bool:
    """
    Publish a message to the Redis pub/sub channel.

    Args:
        payload: Dictionary containing the message data
        redis_host: Redis server hostname (default: localhost)
        redis_port: Redis server port (default: 6379)
        redis_db: Redis database number (default: 0)
        channel: Redis pub/sub channel name (default: sniper_rules)

    Returns:
        bool: True if published successfully, False otherwise
    """
    try:
        r = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        data_str = json.dumps(payload)
        result = r.publish(channel, data_str)

        if result > 0:
            print(f"Published to {result} subscriber(s): '{channel}'")
            print(f"  Payload: {data_str}")
        else:
            print(f"Published but no active subscribers: '{channel}'")
            print(f"  Payload: {data_str}")
        return True

    except redis.ConnectionError as e:
        print(f"Failed to connect to Redis at {redis_host}:{redis_port}: {e}")
        return False
    except Exception as e:
        print(f"Failed to publish message: {e}")
        return False


def push_rule(
    rule_type: str,
    rule_data: Dict[str, Any],
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    channel: str = "sniper_rules",
) -> bool:
    """
    Pushes a new dynamic rule to the running chain-sniper
    bot via Redis Pub/Sub.

    Args:
        rule_type: Type of rule ('log' or 'tx')
        rule_data: Dictionary containing rule filter conditions
        redis_host: Redis server hostname (default: localhost)
        redis_port: Redis server port (default: 6379)
        redis_db: Redis database number (default: 0)
        channel: Redis pub/sub channel name (default: sniper_rules)

    Returns:
        bool: True if rule was pushed successfully, False otherwise
    """
    payload = rule_data.copy()
    payload["action"] = "add"
    payload["type"] = rule_type
    return publish_message(payload, redis_host, redis_port, redis_db, channel)


def remove_rule_by_id(
    rule_id: str,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    channel: str = "sniper_rules",
) -> bool:
    """
    Remove a rule by its ID via Redis Pub/Sub.

    Args:
        rule_id: The UUID of the rule to remove
        redis_host: Redis server hostname (default: localhost)
        redis_port: Redis server port (default: 6379)
        redis_db: Redis database number (default: 0)
        channel: Redis pub/sub channel name (default: sniper_rules)

    Returns:
        bool: True if message was published successfully, False otherwise
    """
    payload = {
        "action": "remove",
        "rule_id": rule_id,
    }
    print(f"\nRemoving rule: {rule_id}")
    return publish_message(payload, redis_host, redis_port, redis_db, channel)


def clear_rules(
    rule_type: str,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    channel: str = "sniper_rules",
) -> bool:
    """
    Clear all rules of a given type via Redis Pub/Sub.

    Args:
        rule_type: Type of rules to clear ('tx' or 'log')
        redis_host: Redis server hostname (default: localhost)
        redis_port: Redis server port (default: 6379)
        redis_db: Redis database number (default: 0)
        channel: Redis pub/sub channel name (default: sniper_rules)

    Returns:
        bool: True if message was published successfully, False otherwise
    """
    payload = {
        "action": "clear",
        "rule_type": rule_type,
    }
    print(f"\nClearing all {rule_type} rules...")
    return publish_message(payload, redis_host, redis_port, redis_db, channel)


def push_log_rule_example():
    """Example: Monitor ERC20 Transfer events for USDT token."""
    print("\n=== Example: ERC20 Transfer Log Rule ===")
    print("Monitoring USDT Transfer events...")

    # USDT contract address on BSC
    usdt_address = "0x55d398326f99059fF775485246999027B3197955"

    push_rule("log", {"address": usdt_address, "target_topic": TRANSFER_TOPIC})


def push_tx_rule_example():
    """Example: Monitor transactions with value less than 1 ETH."""
    print("\n=== Example: Transaction Value Filter Rule ===")
    print("Monitoring transactions with value < 1 ETH...")

    push_rule(
        "tx",
        {
            "value": {
                "_op": "$gte",
                "_value": 1000000000000000000,  # 1 ETH in wei
            }
        },
    )


def push_erc20_transfer_rule():
    """Example: Monitor specific ERC20 token transfers."""
    print("\n=== Example: ERC20 Token Transfer Rule ===")

    # Example: Monitor BUSD transfers
    busd_address = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"

    print(f"Monitoring BUSD transfers at {busd_address}...")
    push_rule("log", {"address": busd_address, "target_topic": TRANSFER_TOPIC})


def push_nft_transfer_rule():
    """Example: Monitor NFT Transfer events (ERC721)."""
    print("\n=== Example: NFT Transfer Rule ===")

    # Example: Monitor BAYC NFT transfers
    bayc_address = "0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D"

    print(f"Monitoring BAYC NFT transfers at {bayc_address}...")
    push_rule("log", {"address": bayc_address, "target_topic": TRANSFER_TOPIC})


def push_batch_rules():
    """Example: Push multiple rules at once."""
    print("\n=== Example: Batch Rule Push ===")
    print("Pushing multiple monitoring rules...")

    rules = [
        # Monitor USDT transfers
        (
            "log",
            {
                "address": "0x55d398326f99059fF775485246999027B3197955",
                "target_topic": TRANSFER_TOPIC,
            },
        ),
        # Monitor BUSD transfers
        (
            "log",
            {
                "address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
                "target_topic": TRANSFER_TOPIC,
            },
        ),
        # Monitor small transactions
        ("tx", {"value": {"_op": "$lt", "_value": 100000000000000000}}),
    ]

    success_count = 0
    for rule_type, rule_data in rules:
        if push_rule(rule_type, rule_data):
            success_count += 1

    print(f"\nSuccessfully pushed {success_count}/{len(rules)} rules")


def push_custom_rule():
    """Example: Push a custom rule with user-defined parameters."""
    print("\n=== Example: Custom Rule ===")

    # Custom log rule: Monitor any contract's specific event
    custom_address = input(
        "Enter contract address (or press Enter for example): "
    ).strip()
    if not custom_address:
        # PancakeSwap Router
        custom_address = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

    custom_topic = input(
        "Enter event topic hash (or press Enter for Transfer): "
    ).strip()
    if not custom_topic:
        custom_topic = TRANSFER_TOPIC

    print(f"Monitoring {custom_address} for event {custom_topic}...")
    push_rule("log", {"address": custom_address, "target_topic": custom_topic})


def remove_rule_example():
    """Example: Remove a rule by its rule_id."""
    print("\n=== Remove Rule ===")

    rule_id = input("Enter rule_id to remove: ").strip()
    if not rule_id:
        print("No rule_id provided. Skipping.")
        return

    remove_rule_by_id(rule_id)


def clear_tx_rules_example():
    """Clear all transaction rules."""
    print("\n=== Clear All TX Rules ===")
    clear_rules("tx")


def clear_log_rules_example():
    """Clear all log rules."""
    print("\n=== Clear All Log Rules ===")
    clear_rules("log")


def clear_all_rules_example():
    """Clear all rules (tx and log)."""
    print("\n=== Clear All Rules ===")
    clear_rules("tx")
    clear_rules("log")


def main():
    """Main entry point for the example script."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable actions: ",
              "log, tx, erc20, nft, batch, custom, remove,"
              )
        print("clear-tx, clear-log, clear-all")
        sys.exit(1)

    action = sys.argv[1].lower()

    actions = {
        "log": push_log_rule_example,
        "tx": push_tx_rule_example,
        "erc20": push_erc20_transfer_rule,
        "nft": push_nft_transfer_rule,
        "batch": push_batch_rules,
        "custom": push_custom_rule,
        "remove": remove_rule_example,
        "clear-tx": clear_tx_rules_example,
        "clear-log": clear_log_rules_example,
        "clear-all": clear_all_rules_example,
    }

    if action in actions:
        actions[action]()
    else:
        print(f"Unknown action: {action}")
        print(f"Available actions: {', '.join(actions.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
