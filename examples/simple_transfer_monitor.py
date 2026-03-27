#!/usr/bin/env python3
"""
Simple ERC20 Transfer Monitor using Chain Sniper modules.

This example demonstrates the modular architecture with reusable utilities.
"""

import asyncio

# Import from the new modular utilities
from chain_sniper.utils import (
    get_rpc_url,
    setup_logging,
    create_websocket_listener,
    create_http_listener,
    create_transfer_handler,
    run_listener,
)
from chain_sniper.contracts import get_contract_abi, get_contract_address


async def main():
    """Main function demonstrating modular Chain Sniper usage."""

    # 1. Configuration and Logging
    rpc_url = get_rpc_url()
    logger = setup_logging(level="INFO", logger_name="transfer-monitor")

    # 2. Choose listener type (WebSocket for real-time, HTTP for polling)
    use_websocket = True  # Set to False for HTTP polling

    if use_websocket:
        listener = create_websocket_listener(rpc_url, logger=logger)
        listener_type = "WebSocket"
    else:
        listener = create_http_listener(rpc_url, logger=logger, poll_interval=2.0)
        listener_type = "HTTP Polling"

    # 3. Get contract information from registry
    try:
        contract_address = get_contract_address("USDT_BSC", "mainnet")
        contract_abi = get_contract_abi("ERC20")
        token_symbol = "USDT"
    except ValueError:
        # Fallback to manual setup if registry not available
        contract_address = "0x55d398326f99059fF775485246999027B3197955"
        from chain_sniper.utils.abis import load_abi_from_file
        import os

        abi_path = os.path.join(os.path.dirname(__file__), "abis", "erc20.json")
        contract_abi = load_abi_from_file(abi_path)
        token_symbol = "USDT"

    # 4. Add ABI-based log filter (automatically decodes events!)
    listener.add_abi_log_filter(
        abi=contract_abi, address=contract_address, event_name="Transfer"
    )

    # 5. Register event handlers
    from chain_sniper.utils.handlers import create_block_handler, create_error_handler

    listener.on("block", create_block_handler(verbose=True))
    listener.on("log", create_transfer_handler(token_symbol=token_symbol))
    listener.on("error", create_error_handler(verbose=True))

    # 6. Run the listener
    await run_listener(
        listener=listener,
        startup_message=f"Starting {listener_type} ERC20 Transfer Monitor...",
        shutdown_message=f"{listener_type} monitor stopped.",
    )


if __name__ == "__main__":
    asyncio.run(main())
