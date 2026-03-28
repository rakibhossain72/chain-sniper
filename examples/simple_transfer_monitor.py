#!/usr/bin/env python3
"""
Simple ERC20 Transfer Monitor using Chain Sniper.

This example demonstrates how to monitor ERC20 transfers with a custom ABI.
"""

import asyncio
from chain_sniper import ChainSniper

# Custom ERC20 ABI for Transfer event
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]


async def on_transfer(log):
    """Handle decoded transfer events."""
    args = log["args"]
    amount = args["value"] / 10**18
    print(f"USDT Transfer: {args['from']} → {args['to']}: {amount:.2f} USDT")


async def main():
    """Monitor USDT transfers on BSC with automatic decoding."""

    # Create sniper with RPC URL (auto-detects WebSocket vs HTTP)
    sniper = (
        ChainSniper("wss://bnb-mainnet.g.alchemy.com/v2/zVuCDSrlJMGM9_S0BiKXa")
        .watch(
            abi=ERC20_ABI,
            address="0x55d398326f99059fF775485246999027B3197955",
            event="Transfer",
        )
        .on_event(on_transfer)
    )

    print("Starting USDT Transfer Monitor... (Ctrl+C to stop)")
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
