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


POA_CHAIN_IDS = {
    56,      # BSC Mainnet
    97,      # BSC Testnet
    137,     # Polygon Mainnet
    80002,   # Polygon Amoy Testnet (Replaced Mumbai 80001)
    250,     # Fantom Opera Mainnet
    4002,    # Fantom Opera Testnet
    100,     # Gnosis Mainnet
    10200,   # Gnosis Chiado Testnet
}


def needs_poa_middleware(chain_id: int | None) -> bool:
    """
    Check if a chain requires ExtraDataToPOAMiddleware.

    Args:
        chain_id: The chain ID to check. If None, returns False.

    Returns:
        True if the chain needs POA middleware, False otherwise.
    """
    if chain_id is None:
        return False
    return chain_id in POA_CHAIN_IDS
