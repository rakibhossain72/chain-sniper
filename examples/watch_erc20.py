import asyncio

# Using the new modular utilities
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper import ChainSniper
from chain_sniper.filters import Filter
from chain_sniper.utils.abis import load_abi_from_file

# Custom ERC20 ABI for Transfer event
ERC20_ABI = load_abi_from_file("examples/abis/erc20.json")

# USDT contract address on BSC
USDT = "0x55d398326f99059fF775485246999027B3197955"


async def main() -> None:
    # Load configuration and setup logging
    rpc_url = get_rpc_url()
    logger = setup_logging(level="INFO", logger_name="example")

    # Create sniper with RPC URL
    sniper = ChainSniper(rpc_url, chain_id=56)

    filter = Filter()
    filter.add_abi(ERC20_ABI, address=USDT)

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

    print("Starting WebSocket listener... (Ctrl+C to stop)")
    await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
