import asyncio
import logging
from typing import Any, Callable, Awaitable


class EventDispatcher:
    """
    Thin wrapper that fires registered callbacks as independent asyncio tasks,
    ensuring that a slow or blocking callback never stalls the listener loop.
    """

    def __init__(
        self,
        listeners: dict[str, list[Callable[..., Awaitable[None]]]],
        logger: logging.Logger,
    ) -> None:
        self._listeners = listeners
        self.logger = logger

    async def emit(self, event: str, payload: Any) -> None:
        """Schedule each callback as a separate task (non-blocking)."""
        for cb in self._listeners.get(event, []):
            asyncio.create_task(self._safe_call(cb, event, payload))

    async def _safe_call(
        self, cb: Callable[..., Awaitable[None]], event: str, payload: Any
    ) -> None:
        try:
            await cb(payload)
        except Exception as exc:
            self.logger.exception(
                "Callback raised for event '%s': %s", event, exc
            )
