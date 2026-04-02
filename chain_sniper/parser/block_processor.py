import asyncio
import logging
from typing import Any, Callable, Awaitable


class BlockProcessor:
    """
    Handles emitting block and transaction events after a full block has been
    fetched.  Reorg detection lives here so it is isolated from transport logic.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._last_block_hash: str | None = None

    def reset(self) -> None:
        """Reset state after a reconnect so we don't false-positive on reorgs."""
        self._last_block_hash = None

    async def process(
        self,
        block: Any,
        emit_fn: Callable[[str, Any], Awaitable[None]],
    ) -> None:
        """
        Check for chain reorgs, emit the block event, then emit each tx.
        """
        parent_hash = block.get("parentHash")
        if isinstance(parent_hash, bytes):
            parent_hash = "0x" + parent_hash.hex()

        if self._last_block_hash is not None and parent_hash != self._last_block_hash:
            self.logger.warning(
                "Chain reorg detected at block %s: expected_parent=%s actual_parent=%s",
                block.get("number"),
                self._last_block_hash,
                parent_hash,
            )
            asyncio.create_task(
                emit_fn(
                    "reorg",
                    {
                        "detected_at_block": block.get("number"),
                        "expected_parent": self._last_block_hash,
                        "actual_parent": parent_hash,
                    },
                )
            )

        block_hash = block.get("hash")
        if isinstance(block_hash, bytes):
            block_hash = "0x" + block_hash.hex()
        self._last_block_hash = block_hash

        asyncio.create_task(emit_fn("block", block))
        for tx in block.get("transactions", []):
            asyncio.create_task(emit_fn("transaction", tx))
