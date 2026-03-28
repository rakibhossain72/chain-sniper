"""
RPC node state model.
"""

from dataclasses import dataclass
from time import time


@dataclass
class RpcNode:
    url: str
    latency: float = (
        999.0  # moving average ms;
    )
    error_count: int = 0
    cooldown_until: float = 0.0  # epoch seconds
    is_dead: bool = False

    @property
    def is_healthy(self) -> bool:
        return not self.is_dead and time() >= self.cooldown_until

    def record_success(self, elapsed_ms: float) -> None:
        """Exponential moving average — weights recent latency more."""
        self.latency = (self.latency + elapsed_ms) / 2
        self.error_count = 0

    def mark_failed(self, cooldown_seconds: float = 30.0) -> None:
        self.error_count += 1
        self.cooldown_until = time() + cooldown_seconds
        if self.error_count >= 5:
            self.is_dead = True

    def revive(self) -> None:
        self.is_dead = False
        self.error_count = 0
        self.cooldown_until = 0.0
