import asyncio

# Using the new modular utilities
from chain_sniper.utils.config import get_rpc_url
from chain_sniper.utils.logging import setup_logging
from chain_sniper.utils.runner import create_websocket_listener, run_listener
from chain_sniper.utils.handlers import (
    create_block_handler,
    create_log_handler,
    create_error_handler,
)
from chain_sniper.contracts import get_contract_abi, get_contract_address


async def main() -> None:
    # Load configuration and setup logging
    rpc_url = get_rpc_url()
    logger = setup_logging(level="INFO", logger_name="example")

    # Create WebSocket listener using utility function
    listener = create_websocket_listener(
        rpc_url=rpc_url,
        block_detail="full_block",
        logger=logger,
    )

    # Get contract details from registry
    usdt_address = get_contract_address("USDT_BSC", "mainnet")
    erc20_abi = get_contract_abi("ERC20")

    # Add ABI-based log filter - automatically decodes logs!
    listener.add_abi_log_filter(
        abi=erc20_abi, address=usdt_address, event_name="Transfer"
    )

    # Alternative: Add filter using topic hash (returns raw logs)
    # listener.add_abi_log_filter(
    #     address=usdt_address,
    #     topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"]
    # )

    # Register event handlers using utility functions
    listener.on("block", create_block_handler())
    listener.on("log", create_log_handler())
    listener.on("error", create_error_handler())

    # Run the listener with proper error handling
    await run_listener(
        listener=listener,
        startup_message="Starting WebSocket listener...",
        shutdown_message="WebSocket listener stopped.",
    )


if __name__ == "__main__":
    asyncio.run(main())
