import asyncio
import logging
from typing import Any, Callable, Awaitable


class BlockProcessor:
    """
    Handles emitting block and transaction events after a full block has been
    fetched.  Reorg detection lives here so it is isolated from transport logic.

    Works for both FULL_BLOCK (transactions available) and HEADER-only mode
    (transactions list will be empty or contain only hashes).
    """

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._last_block_hash: str | None = None

    def reset(self) -> None:
        """Reset state after a reconnect so we don't false-positive on reorgs."""
        self._last_block_hash = None

    def _normalise_hash(self, value: Any) -> str | None:
        """Normalise HexBytes or plain str to a lowercase 0x-prefixed hex string."""
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            return "0x" + value.hex()
        return str(value)

    async def process(
        self,
        block: Any,
        emit_fn: Callable[[str, Any], Awaitable[None]],
    ) -> None:
        """
        Check for chain reorgs, emit the block event, then emit each tx.

        All emit calls are dispatched as independent asyncio tasks so this
        method returns immediately without waiting for callbacks to complete.
        This keeps the block worker loop unblocked even if a callback is slow.
        """
        parent_hash = self._normalise_hash(block.get("parentHash"))
        block_hash = self._normalise_hash(block.get("hash"))

        # --- Reorg detection ---
        # Compare this block's parentHash against the hash we stored for the
        # previous block.  A mismatch means the chain reorganised and we are
        # now on a different fork.  We emit a "reorg" event and continue
        # processing the new canonical block — callers are responsible for
        # rolling back any state they built on the orphaned chain.
        if self._last_block_hash is not None and parent_hash != self._last_block_hash:
            self.logger.warning(
                "Chain reorg detected at block %s: expected_parent=%s actual_parent=%s",
                block.get("number"),
                self._last_block_hash,
                parent_hash,
            )
            # Non-blocking: reorg handler must not stall block processing
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

        # Advance the chain tip regardless of reorg so subsequent blocks are
        # checked against the correct parent.
        self._last_block_hash = block_hash

        # Non-blocking block event — callbacks run in their own tasks
        asyncio.create_task(emit_fn("block", block))

        # Emit individual transactions only when full objects are present.
        # In HEADER mode, transactions is either absent or contains only hashes
        # (strings), so we skip emission to avoid confusing callers.
        for tx in block.get("transactions", []):
            if isinstance(tx, (str, bytes)):
                # Hash-only — not useful as a transaction event
                continue
            asyncio.create_task(emit_fn("transaction", tx))
