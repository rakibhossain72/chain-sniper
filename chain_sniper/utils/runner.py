"""
Runner utilities for starting listeners with proper error handling.
"""

import asyncio
from typing import Any, Optional
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.poll_listener import HttpListener
from chain_sniper.listener.common import BlockDetail


async def run_listener(
    listener: WebSocketListener | HttpListener,
    startup_message: str = "Starting listener...",
    shutdown_message: str = "Listener stopped.",
) -> None:
    """
    Run a listener with proper error handling and graceful shutdown.

    Args:
        listener: The listener instance to run
        startup_message: Message to print when starting
        shutdown_message: Message to print when stopping
    """
    print(f"{startup_message}\n")

    try:
        await listener.start()
    except KeyboardInterrupt:
        print(f"\n{shutdown_message}")
        listener.stop()
    except Exception as exc:
        print(f"Fatal error: {exc}")
        listener.stop()


def create_websocket_listener(
    rpc_url: str,
    block_detail: str = "full_block",
    logger: Optional[Any] = None,
    **kwargs,
) -> WebSocketListener:
    """
    Create a WebSocket listener with common settings.

    Args:
        rpc_url: WebSocket RPC URL
        block_detail: Block detail level ("header" or "full_block")
        logger: Logger instance
        **kwargs: Additional arguments for WebSocketListener

    Returns:
        Configured WebSocketListener instance
    """
    block_detail_enum = (
        BlockDetail.FULL_BLOCK if block_detail == "full_block" else BlockDetail.HEADER
    )

    return WebSocketListener(
        rpc_url=rpc_url, block_detail=block_detail_enum, logger=logger, **kwargs
    )


def create_http_listener(
    rpc_url: str,
    block_detail: str = "full_block",
    logger: Optional[Any] = None,
    poll_interval: float = 2.0,
    **kwargs,
) -> HttpListener:
    """
    Create an HTTP polling listener with common settings.

    Args:
        rpc_url: HTTP RPC URL
        block_detail: Block detail level ("header" or "full_block")
        logger: Logger instance
        poll_interval: Polling interval in seconds
        **kwargs: Additional arguments for HttpListener

    Returns:
        Configured HttpListener instance
    """
    block_detail_enum = (
        BlockDetail.FULL_BLOCK if block_detail == "full_block" else BlockDetail.HEADER
    )

    return HttpListener(
        rpc_url=rpc_url,
        block_detail=block_detail_enum,
        logger=logger,
        poll_interval=poll_interval,
        **kwargs,
    )
