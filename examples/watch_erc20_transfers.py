"""
Watch ERC20 Transfer events on BSC using the decorator API.

Set RPC_URL=wss://... in your .env file before running.

    python examples/watch_erc20_transfers.py
"""

import asyncio
from chain_sniper import ChainSniper
from chain_sniper.utils.config import get_rpc_url
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

# USDT on BSC
USDT = "0x55d398326f99059fF775485246999027B3197955"


async def main():
    logger = setup_logging(level="INFO", logger_name="watch-erc20")
    sniper = ChainSniper(get_rpc_url())

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

    logger.info("Listening for USDT transfers on BSC...")
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
