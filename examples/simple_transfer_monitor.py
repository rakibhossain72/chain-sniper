#!/usr/bin/env python3
"""
Simple ERC20 Transfer Monitor using Chain Sniper.

This example demonstrates the new decorator-based ChainSniper API
with fault-tolerant RPC pool.
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.rpc_pool import RPCPool

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

# BSC RPC endpoints (multiple for fault tolerance)
BSC_RPCS = [
    "wss://bsc-ws-node.nariox.org:443",
    "wss://bsc-dataseed.binance.org/",
]

# BSC Chain ID
BSC_CHAIN_ID = 56


async def main():
    """Monitor USDT transfers on BSC with automatic decoding."""

    # Create RPC pool with multiple endpoints for fault tolerance
    pool = await RPCPool.create(
        rpcs=[
            "https://bsc-dataseed1.binance.org",
            "https://binance.llamarpc.com",
            "https://public-bsc-mainnet.fastnode.io",
            "https://rpc.owlracle.info/bsc/70d38ce1826c4a60bb2a8e05a6c8b20f",
            "https://bsc-dataseed2.ninicoin.io",
            "https://bsc-dataseed2.defibit.io",
        ],
        expected_chain_id=56,
    )
    sniper = ChainSniper(pool)

    @sniper.event(
        contract=USDT,
        abi=ERC20_ABI,
        name="Transfer"
    )
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
