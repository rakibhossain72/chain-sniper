from abc import ABC, abstractmethod
from typing import Any

class BaseFilter(ABC):

    @abstractmethod
    def match(self, tx: Any) -> bool:
        ...
    
    @abstractmethod
    def match_log(self, log: Any) -> bool:
        ...
