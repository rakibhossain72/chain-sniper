"""
Example script for pushing dynamic rules to chain-sniper via Redis Pub/Sub.

This script demonstrates how to dynamically add, remove, and clear filtering
rules in a running chain-sniper instance without restarting the bot. Rules are
published to a Redis channel and consumed by the RedisRuleListener
in real-time.

Usage:
    python examples/push_redis_rule.py [action]

Actions:
    log              - Push a log post-filter rule (local filter)
    log_subscription - Push a log subscription rule (node-level filter)
    tx               - Push a transaction filter rule
    erc20            - Push an ERC20 transfer monitor rule
    nft              - Push an NFT transfer monitor rule
    batch            - Push multiple rules at once
    custom           - Push a custom rule with user-defined parameters
    remove           - Remove a rule by its rule_id
    clear-tx         - Clear all transaction rules
    clear-log        - Clear all log post-filter rules
    clear-sub        - Clear all log subscriptions
    clear-all        - Clear all rules (tx, log, and subscriptions)

Examples:
    # Monitor USDT transfers using node-side subscription
    python examples/push_redis_rule.py erc20

    # Monitor transactions with value >= 1 ETH
    python examples/push_redis_rule.py tx

    # Push multiple rules at once
    python examples/push_redis_rule.py batch

    # Remove a specific rule by ID
    python examples/push_redis_rule.py remove <rule_id>
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
    Pushes a new dynamic rule or subscription to the running chain-sniper
    bot via Redis Pub/Sub.
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
    Remove a rule or subscription by its ID via Redis Pub/Sub.
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
    Clear all rules or subscriptions of a given type via Redis Pub/Sub.
    """
    payload = {
        "action": "clear",
        "rule_type": rule_type,
    }
    print(f"\nClearing all {rule_type}...")
    return publish_message(payload, redis_host, redis_port, redis_db, channel)


def push_log_post_filter_example():
    """Example: Local log filtering on address."""
    print("\n=== Example: Log Post-filter Rule ===")
    usdt_address = "0x55d398326f99059fF775485246999027B3197955"
    push_rule("log", {"address": usdt_address})


def push_log_subscription_example():
    """Example: Node-side log subscription."""
    print("\n=== Example: Log Subscription Rule ===")
    usdt_address = "0x55d398326f99059fF775485246999027B3197955"
    push_rule("log_subscription", {"address": usdt_address, "topics": [TRANSFER_TOPIC]})


def push_tx_rule_example():
    """Example: Monitor transactions with value >= 1 BNB."""
    print("\n=== Example: Transaction Value Filter Rule ===")
    push_rule(
        "tx",
        {
            "value": {
                "_op": "$gte",
                "_value": 1000000000000000000,  # 1 BNB in wei
            }
        },
    )


def push_erc20_subscription():
    """Example: Use node-side subscription for ERC20 transfers."""
    print("\n=== Example: ERC20 Log Subscription ===")
    usdt_address = "0x55d398326f99059fF775485246999027B3197955"
    push_rule("log_subscription", {"address": usdt_address, "topics": [TRANSFER_TOPIC]})


def push_nft_subscription():
    """Example: Use node-side subscription for NFT transfers."""
    print("\n=== Example: NFT Log Subscription ===")
    bayc_address = "0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D"
    push_rule("log_subscription", {"address": bayc_address, "topics": [TRANSFER_TOPIC]})


def push_batch_rules():
    """Example: Push multiple rules at once."""
    print("\n=== Example: Batch Rule Push ===")
    rules = [
        # Subscription for USDT
        (
            "log_subscription",
            {
                "address": "0x55d398326f99059fF775485246999027B3197955",
                "topics": [TRANSFER_TOPIC],
            },
        ),
        # Transactions >= 0.1 BNB
        ("tx", {"value": {"_op": "$gte", "_value": 100000000000000000}}),
    ]

    success_count = 0
    for rule_type, rule_data in rules:
        if push_rule(rule_type, rule_data):
            success_count += 1
    print(f"\nSuccessfully pushed {success_count}/{len(rules)} rules")


def push_custom_rule():
    """Example: Push a custom rule with user-defined parameters."""
    print("\n=== Example: Custom Rule ===")
    custom_address = input("Enter contract address: ").strip()
    custom_topic = input("Enter event topic hash: ").strip()
    print(f"Subscribing to {custom_address} for event {custom_topic}...")
    push_rule("log_subscription", {"address": custom_address, "topics": [custom_topic]})


def remove_rule_example():
    """Example: Remove a rule by its rule_id."""
    print("\n=== Remove Rule ===")
    rule_id = input("Enter rule_id to remove: ").strip()
    if not rule_id:
        return
    remove_rule_by_id(rule_id)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()
    actions = {
        "log": push_log_post_filter_example,
        "log_subscription": push_log_subscription_example,
        "tx": push_tx_rule_example,
        "erc20": push_erc20_subscription,
        "nft": push_nft_subscription,
        "batch": push_batch_rules,
        "custom": push_custom_rule,
        "remove": remove_rule_example,
        "clear-tx": lambda: clear_rules("tx"),
        "clear-log": lambda: clear_rules("log"),
        "clear-sub": lambda: clear_rules("log_subscription"),
        "clear-all": lambda: (clear_rules("tx"), clear_rules("log"), clear_rules("log_subscription")),
    }

    if action in actions:
        actions[action]()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
