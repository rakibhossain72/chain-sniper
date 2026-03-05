from abc import ABC, abstractmethod
from typing import Any

class BaseStrategy(ABC):

    @abstractmethod
    async def execute(self, data: Any) -> None:
        ...
    
    async def execute_log(self, log: Any) -> None:
        ...
