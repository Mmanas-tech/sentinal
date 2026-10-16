"""Small in-process event bus used by the Phase 1 scaffold."""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from .schemas import Event

Handler = Callable[[Event], Awaitable[Any] | Any]
EventKey = tuple[str, str]


class EventBus:
    """Dispatch events once per ``source_id`` and event ID."""

    def __init__(self) -> None:
        self._handlers: defaultdict[str, list[Handler]] = defaultdict(list)
        self._seen: set[EventKey] = set()
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> bool:
        """Publish an event, returning ``False`` when it is a duplicate."""
        event_key = (event.source_id, event.id)
        async with self._lock:
            if event_key in self._seen:
                return False
            self._seen.add(event_key)

        handlers = [
            *self._handlers.get(event.type, []),
            *self._handlers.get("*", []),
        ]
        await asyncio.gather(*(self._invoke(handler, event) for handler in handlers))
        return True

    @staticmethod
    async def _invoke(handler: Handler, event: Event) -> None:
        result = handler(event)
        if asyncio.iscoroutine(result):
            await result
