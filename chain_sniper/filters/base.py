"""
Base classes for filters.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseFilter(ABC):
    """
    Abstract base class for transaction and log filters.
    """

    @abstractmethod
    def match(self, tx: Any) -> bool:
        """
        Check if transaction matches this filter.

        Args:
            tx: Transaction dictionary

        Returns:
            True if transaction matches
        """
        ...

    @abstractmethod
    def match_log(self, log: Any) -> bool:
        """
        Check if log matches this filter.

        Args:
            log: Log dictionary (may be raw or decoded)

        Returns:
            True if log matches
        """
        ...
