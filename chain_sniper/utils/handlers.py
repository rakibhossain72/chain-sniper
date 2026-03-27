"""
Common event handlers for listeners.
"""

from typing import Callable, Dict, Any


from typing import Callable, Awaitable, Dict, Any


def create_block_handler(
    verbose: bool = True,
) -> Callable[[Dict[str, Any]], Awaitable[None]]:
    """
    Create a block event handler.

    Args:
        verbose: Whether to print block information

    Returns:
        Async function that handles block events
    """

    async def on_block(block: Dict[str, Any]) -> None:
        """Handle new block events."""
        if verbose:
            tx_count = len(block.get("transactions", []))
            number = int(block["number"], 16)
            print(f"[BLOCK] #{number:,}  hash={block['hash'][:12]}…  txs={tx_count}")

    return on_block


def create_log_handler(
    verbose: bool = True, exit_after_first: bool = False
) -> Callable[[Dict[str, Any]], Awaitable[None]]:
    """
    Create a log event handler.

    Args:
        verbose: Whether to print detailed log information
        exit_after_first: Whether to exit after processing first log (for testing)

    Returns:
        Async function that handles log events
    """

    async def on_log(log: Dict[str, Any]) -> None:
        """Handle log events."""
        if exit_after_first:
            print(log)
            exit(0)

        if verbose:
            addr = log.get("address", "???")
            # Check if log is decoded
            if "event" in log:
                # Decoded log
                event_name = log.get("event")
                args = log.get("args", {})
                print(f"[LOG] {addr[:8]}… → {event_name}: {args}")
            else:
                # Raw log
                topics = log.get("topics", [])
                first_topic = topics[0][:10] + "…" if topics else "no-topic"
                print(f"[LOG] {addr[:8]}… → {first_topic}")

    return on_log


def create_error_handler(
    verbose: bool = True,
) -> Callable[[Exception], Awaitable[None]]:
    """
    Create an error event handler.

    Args:
        verbose: Whether to print error information

    Returns:
        Async function that handles error events
    """

    async def on_error(exc: Exception) -> None:
        """Handle error events."""
        if verbose:
            print(f"[ERROR] {type(exc).__name__}: {exc}")

    return on_error


def create_transfer_handler(
    token_symbol: str = "TOKEN",
) -> Callable[[Dict[str, Any]], Awaitable[None]]:
    """
    Create a handler specifically for ERC20 Transfer events.

    Args:
        token_symbol: Symbol of the token for display

    Returns:
        Async function that handles Transfer events
    """

    async def on_transfer_log(log: Dict[str, Any]) -> None:
        """Handle Transfer event logs."""
        if "event" in log and log["event"] == "Transfer":
            args = log.get("args", {})
            amount = args.get("value", 0)
            if isinstance(amount, int):
                # Convert from wei if it's a large number
                if amount > 10**18:
                    amount = amount / (10**18)
                print(
                    f"[TRANSFER] {args.get('from')} → {args.get('to')}: {amount} {token_symbol}"
                )
            else:
                print(
                    f"[TRANSFER] {args.get('from')} → {args.get('to')}: {amount} {token_symbol}"
                )
        else:
            # Fallback for raw logs
            addr = log.get("address", "???")
            topics = log.get("topics", [])
            first_topic = topics[0][:10] + "…" if topics else "no-topic"
            print(f"[LOG] {addr[:8]}… → {first_topic}")

    return on_transfer_log
