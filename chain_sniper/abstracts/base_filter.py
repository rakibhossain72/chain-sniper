"""
Abstract base classes for filters.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTransactionFilter(ABC):
    """Abstract base for transaction / block filters."""

    @abstractmethod
    def match(self, tx: Any) -> bool: ...

    @abstractmethod
    def add_rule(self, rule: dict) -> str: ...

    @abstractmethod
    def remove_rule(self, rule_id: str) -> bool: ...


class BaseLogFilter(ABC):
    """Abstract base for log subscription + post-filter managers."""

    @abstractmethod
    def subscribe(self, **kwargs) -> str: ...

    @abstractmethod
    def unsubscribe(self, sub_id: str) -> bool: ...

    @abstractmethod
    def match(self, log: Any) -> bool: ...
