"""
Shared types, protocols, and type aliases for Chain Sniper.
"""

from enum import Enum
from typing import Callable, Awaitable, Any, Dict, Protocol, runtime_checkable


class BlockDetail(str, Enum):
    """Controls how much block data is fetched."""

    HEADER = "header"
    FULL_BLOCK = "full_block"


# Callback type aliases
EventCallback = Callable[[dict], Awaitable[None]]
BlockCallback = Callable[[dict], Awaitable[None]]
ErrorCallback = Callable[[Exception], Awaitable[None]]
TxCallback = Callable[[dict], Awaitable[None]]
ReorgCallback = Callable[[dict], Awaitable[None]]
FilterFn = Callable[[dict], bool]


@runtime_checkable
class TransactionFilterProtocol(Protocol):
    """Protocol for transaction filter objects."""

    def match(self, tx: dict) -> bool: ...
    def add_rule(self, rule: dict) -> str: ...
    def remove_rule(self, rule_id: str) -> bool: ...


@runtime_checkable
class LogFilterProtocol(Protocol):
    """Protocol for log filter objects."""

    def subscribe(self, **kwargs) -> str: ...
    def unsubscribe(self, sub_id: str) -> bool: ...
    def match(self, log: dict) -> bool: ...
