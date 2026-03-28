#!/usr/bin/env python3
"""
Simple ERC20 Transfer Monitor using Chain Sniper.

This example demonstrates the new decorator-based ChainSniper API.
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.utils.config import get_rpc_url

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

# USDT contract address on BSC
USDT = "0x55d398326f99059fF775485246999027B3197955"


async def main():
    """Monitor USDT transfers on BSC with automatic decoding."""

    # Create sniper with RPC URL (auto-detects WebSocket vs HTTP)
    sniper = ChainSniper(get_rpc_url())

    @sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
    async def transfer_handler(event) -> None:
        """Handle decoded transfer events."""
        args = event["args"]
        amount = args["value"] / 10**18
        print(
            f"USDT Transfer: {args['from']} → {args['to']}: {amount:.2f} USDT"
            )

    print("Starting USDT Transfer Monitor... (Ctrl+C to stop)")
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
