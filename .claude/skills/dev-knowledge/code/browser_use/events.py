"""Event-bus shim for browser events.

Kept dependency-free so any caller can plug in the xpander SDK publisher
later. The default implementation is an unbounded asyncio.Queue.

Usage:
    bus = EventBus()
    await bus.publish(BrowserEvent("page.loaded", page_id, {"url": url}))
    evt = await bus.next("page.loaded")
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional


@dataclass
class BrowserEvent:
    type: str                     # "page.loaded", "page.error", "network.response", "target.crashed"
    page_id: Optional[str] = None  # CDP targetId
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


Publisher = Callable[[BrowserEvent], Awaitable[None]]


class EventBus:
    """Local async fan-out. Set `external_publisher` to forward into
    xpander SDK's event system (or any other transport)."""

    def __init__(self, external_publisher: Optional[Publisher] = None) -> None:
        self._q: asyncio.Queue[BrowserEvent] = asyncio.Queue()
        self._external_publisher = external_publisher

    async def publish(self, event: BrowserEvent) -> None:
        await self._q.put(event)
        if self._external_publisher is not None:
            try:
                await self._external_publisher(event)
            except Exception:
                # Don't let an external bus failure crash the agent.
                pass

    async def next(self, type_filter: Optional[str] = None,
                   timeout: Optional[float] = None) -> BrowserEvent:
        """Await the next event, optionally filtered by type."""
        deadline = None if timeout is None else asyncio.get_event_loop().time() + timeout
        while True:
            remaining = None if deadline is None else max(0.0, deadline - asyncio.get_event_loop().time())
            evt = await asyncio.wait_for(self._q.get(), timeout=remaining)
            if type_filter is None or evt.type == type_filter:
                return evt
