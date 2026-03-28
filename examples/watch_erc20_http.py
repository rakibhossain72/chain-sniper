import asyncio

# Using the new modular utilities
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
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

# USDT contract address on BSC
USDT = "0x55d398326f99059fF775485246999027B3197955"


async def main() -> None:
    # Load configuration and setup logging
    rpc_url = get_rpc_url()
    logger = setup_logging(level="INFO", logger_name="example")

    # Create sniper with RPC URL (HTTP URL = auto HTTP polling)
    sniper = ChainSniper(rpc_url)
    sniper.poll_interval(2.0)

    @sniper.event(
        contract=USDT,
        abi=ERC20_ABI,
        name="Transfer"
    )
    async def transfer_handler(event):
        """Handle decoded transfer events."""
        args = event["args"]
        amount = args["value"] / 10**18
        print(
            f"USDT Transfer: {args['from']} → {args['to']}: {amount:.2f} USDT"
        )

    # Register error handler
    @sniper.on_error
    async def error_handler(error):
        logger.error(f"Error: {error}")

    print("Starting HTTP polling listener... (Ctrl+C to stop)")
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
