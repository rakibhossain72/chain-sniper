"""
Shared types, protocols, and type aliases for Chain Sniper.
"""

from enum import Enum
from typing import Callable, Awaitable, Any, Protocol, runtime_checkable


class BlockDetail(str, Enum):
    """Controls how much block data is fetched."""

    HEADER = "header"
    FULL_BLOCK = "full_block"


# Callback type aliases
EventCallback = Callable[[dict], Awaitable[None]]
BlockCallback = Callable[[dict], Awaitable[None]]
ErrorCallback = Callable[[Exception], Awaitable[None]]
TxCallback = Callable[[dict], Awaitable[None]]
FilterFn = Callable[[dict], bool]


@runtime_checkable
class FilterProtocol(Protocol):
    """Protocol for filter objects."""

    def match(self, tx: dict) -> bool: ...
    def match_log(self, log: dict) -> bool: ...
