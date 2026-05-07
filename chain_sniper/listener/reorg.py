"""
Chain reorganisation detection utilities.

Both WebSocketListener and HttpListener delegate reorg detection to
BlockProcessor, but this module provides a standalone ReorgTracker for
callers that want to track reorg depth or build rollback logic on top of
the "reorg" events emitted by the listeners.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReorgEvent:
    """Payload emitted on the "reorg" listener event."""

    detected_at_block: int | None
    expected_parent: str | None  # hash of the block we thought was canonical
    actual_parent: str | None    # hash the new block claims as its parent


@dataclass
class ReorgTracker:
    """
    Stateful helper that maintains a short window of recent block hashes so
    callers can estimate reorg depth when a reorg event arrives.

    Usage::

        tracker = ReorgTracker(window=64)

        @listener.on("block")
        async def on_block(block):
            tracker.record(block)

        @listener.on("reorg")
        async def on_reorg(event):
            depth = tracker.estimate_depth(event["actual_parent"])
            print(f"Reorg depth ~{depth} blocks")
    """

    window: int = 64
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("ReorgTracker")
    )

    # Internal ring buffer: list of (block_number, block_hash) tuples,
    # newest last.  We keep at most `window` entries.
    _history: list[tuple[int | None, str]] = field(default_factory=list, init=False)

    def record(self, block: Any) -> None:
        """Record a newly seen canonical block."""
        block_hash = block.get("hash")
        if isinstance(block_hash, (bytes, bytearray)):
            block_hash = "0x" + block_hash.hex()
        if not block_hash:
            return
        self._history.append((block.get("number"), str(block_hash)))
        # Trim to window size
        if len(self._history) > self.window:
            self._history = self._history[-self.window :]

    def estimate_depth(self, actual_parent_hash: str) -> int:
        """
        Walk backwards through recorded history to find where the reorged
        chain diverged.  Returns the estimated number of blocks rolled back,
        or -1 if the divergence point is outside the tracked window.
        """
        for depth, (_, recorded_hash) in enumerate(reversed(self._history)):
            if recorded_hash == actual_parent_hash:
                self.logger.info(
                    "Reorg divergence found at depth %d (parent=%s)",
                    depth,
                    actual_parent_hash,
                )
                return depth
        self.logger.warning(
            "Reorg divergence point not found in last %d blocks "
            "(actual_parent=%s) — reorg may be deeper than window",
            self.window,
            actual_parent_hash,
        )
        return -1

    def clear(self) -> None:
        """Reset history — call after a reconnect to avoid stale comparisons."""
        self._history.clear()
