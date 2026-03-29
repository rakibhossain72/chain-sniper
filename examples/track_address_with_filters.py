#!/usr/bin/env python3
"""
Simple Blockchain Address Tracker using ChainSniper
"""

import asyncio
from typing import Any
from chain_sniper import ChainSniper
from chain_sniper.rpc_pool import RPCPool
from chain_sniper.filters import Filter
from chain_sniper.utils.logging import setup_logging

#  Configuration
TRACKED_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"  # USDT on BSC

BSC_RPCS = [
    "https://bsc-dataseed1.binance.org",
    "https://bsc-dataseed2.binance.org",
    "https://bsc-dataseed3.binance.org",
    "https://bsc-dataseed4.binance.org",
    "https://public-bsc-mainnet.fastnode.io",
]

BSC_CHAIN_ID = 56


#  Helper Function
async def create_sniper():
    """Create RPC pool and ChainSniper instance"""
    pool = await RPCPool.create(rpcs=BSC_RPCS, expected_chain_id=BSC_CHAIN_ID)
    return ChainSniper(pool)


#  Example 1: Track incoming transfers to address
async def example_1():
    logger = setup_logging(level="INFO", logger_name="tracker")
    logger.info("=== Tracking Incoming Transfers ===")

    ex1_filter = Filter()
    ex1_filter.add_tx_rule({"to": TRACKED_ADDRESS})

    sniper = await create_sniper()
    sniper = sniper.filter(ex1_filter)
    sniper.block_detail("full_block")

    @sniper.on_block
    async def handle_block(block: dict[str, Any]):
        if not block:
            return
        for tx in block.get("transactions", []):
            if isinstance(tx, str):
                continue
            logger.info(
                f"Block #{int(block['number'], 16)} | "
                f"TX: {tx.get('hash', 'unknown')[:10]}... | "
                f"{tx.get('from', '')[:8]}... → "
                f"{str(tx.get('to', ''))[:8]}... | "
                f"{int(tx.get('value', '0'), 16) / 10**18:.6f} BNB"
            )

    await sniper.start()


#  Example 2: Track calls to a contract
async def example_2():
    logger = setup_logging(level="INFO", logger_name="tracker")
    logger.info("=== Tracking Contract Calls ===")

    sniper = await create_sniper()
    sniper.filter(Filter(target_contract=TRACKED_ADDRESS))
    sniper.block_detail("full_block")

    @sniper.on_block
    async def handle_block(block: dict[str, Any]):
        if not block:
            return
        for tx in block.get("transactions", []):
            if isinstance(tx, str):
                continue
            input_data = tx.get("input", "0x")
            logger.info(
                f"Block #{int(block['number'], 16)} | "
                f"TX: {tx.get('hash', '')[:10]}... | "
                f"Called: {tx.get('to', '')[:8]}... | "
                f"Input: {input_data[:10]}..."
            )

    await sniper.start()


# Example 3: Advanced filtering with rules
async def example_3():
    logger = setup_logging(level="INFO", logger_name="tracker")
    logger.info("=== Advanced Dynamic Filtering ===")

    sniper = await create_sniper()

    f = Filter()
    f.add_tx_rule({"to": TRACKED_ADDRESS})           # To our address
    f.add_tx_rule({"from": TRACKED_ADDRESS})         # From our address
    f.add_tx_rule({"value": {"_op": "$gte", "_value": 10**18}})  # ≥ 1 BNB

    sniper.filter(f)
    sniper.block_detail("full_block")

    @sniper.on_block
    async def handle_block(block: dict[str, Any]):
        if not block:
            return
        for tx in block.get("transactions", []):
            if isinstance(tx, str):
                continue
            logger.info(f"Matched TX: {tx.get('hash', '')[:10]}...")

    await sniper.start()


async def main():
    examples = {
        "1": ("Track Incoming Transfers", example_1),
        "2": ("Track Contract Calls", example_2),
        "3": ("Advanced Filtering", example_3),
    }

    print("\n=== Chain Sniper - Address Tracker ===")
    print("Choose an example to run:\n")
    for num, (name, _) in examples.items():
        print(f"  {num}. {name}")

    choice = "1"  # input("\nEnter number (1-3): ").strip()

    if choice in examples:
        print(f"\nRunning: {examples[choice][0]}")
        print(f"Tracking: {TRACKED_ADDRESS}")
        print("-" * 60)
        await examples[choice][1]()
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
