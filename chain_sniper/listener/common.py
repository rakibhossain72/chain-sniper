"""
Common types and utilities for blockchain listeners.
"""

from enum import Enum


class BlockDetail(str, Enum):
    """Controls how much block data is fetched."""

    HEADER = "header"  # only the block header
    FULL_BLOCK = "full_block"  # header + all transactions


class _IdGen:
    """Thread-safe monotonically increasing JSON-RPC id generator."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n
