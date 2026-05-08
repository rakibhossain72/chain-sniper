"""
Fault-tolerant monitoring using an RPCPool with multiple WebSocket endpoints.

If one endpoint fails, the pool automatically rotates to the next healthy one.

Set at least one of the RPC URLs below, or use RPC_URL from your .env.

    python examples/watch_with_rpc_pool.py
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.rpc_pool import RPCPool
from chain_sniper.utils.logging import setup_logging

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

USDT = "0x55d398326f99059fF775485246999027B3197955"

# Add your WebSocket endpoints here
RPC_ENDPOINTS = [
    "wss://bsc-ws-node.nariox.org:443",
    # "wss://your-backup-rpc.example.com",
]


async def main():
    logger = setup_logging(level="INFO", logger_name="rpc-pool")

    pool = await RPCPool.create(
        rpcs=RPC_ENDPOINTS,
        expected_chain_id=56,  # BSC
    )

    sniper = ChainSniper(pool)

    @sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
    async def on_transfer(event):
        args = event.get("args", {})
        value = args.get("value", 0) / 10**18
        logger.info(
            "Transfer  from=%s  to=%s  value=%.4f USDT",
            args.get("from"),
            args.get("to"),
            value,
        )

    @sniper.on_reorg
    async def on_reorg(event):
        logger.warning("Reorg detected: %s", event)

    @sniper.on_error
    async def on_error(exc):
        logger.error("Error: %s", exc)

    logger.info("Listening with RPC pool (%d endpoints)...", len(RPC_ENDPOINTS))
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
