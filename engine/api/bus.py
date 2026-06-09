"""Thread-safe broadcast event bus for SSE streaming.

The supervisor emits TaskEvents from synchronous threads (FastAPI's thread-pool
workers).  SSE clients live in the asyncio event loop.  This bus bridges the
two worlds via ``asyncio.Queue`` + ``loop.call_soon_threadsafe``.

Usage:
    bus = SSEEventBus()

    # In FastAPI lifespan startup:
    bus.attach_loop(asyncio.get_running_loop())

    # In supervisor constructor:
    supervisor = TaskSupervisor(..., event_bus=bus)

    # In SSE route:
    q = bus.subscribe()
    try:
        event = await asyncio.wait_for(q.get(), timeout=15.0)
        yield f"data: {event.model_dump_json()}\\n\\n"
    finally:
        bus.unsubscribe(q)
"""

from __future__ import annotations

import asyncio
import threading

from engine.interfaces.event import TaskEvent


class SSEEventBus:
    """Broadcast event bus that fans out to all connected SSE subscribers.

    Thread-safe: ``emit()`` may be called from any thread.
    Subscribers receive events via ``asyncio.Queue`` on the attached loop.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[asyncio.Queue[TaskEvent | None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the running asyncio event loop.

        Call this once from the FastAPI/uvicorn startup context so that
        ``emit()`` can safely schedule queue puts from synchronous threads.
        """
        self._loop = loop

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[TaskEvent | None]:
        """Return a new per-client queue and register it for broadcasts."""
        q: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[TaskEvent | None]) -> None:
        """Remove a client queue.  Safe to call even if already removed."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def subscriber_count(self) -> int:
        """Return the number of currently connected SSE clients."""
        with self._lock:
            return len(self._subscribers)

    # ------------------------------------------------------------------
    # EventBus protocol
    # ------------------------------------------------------------------

    def emit(self, event: TaskEvent) -> None:
        """Publish an event to all connected subscribers.

        Called from the supervisor's synchronous thread.  Schedules a
        non-blocking queue put on the asyncio event loop via
        ``call_soon_threadsafe``.  Silently drops events when no loop
        is attached (e.g. during tests or before server startup).
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                # Loop closed during shutdown — safe to ignore.
                pass

    def health_check(self) -> list[str]:
        """Return health issues; empty means healthy."""
        return []

    # ------------------------------------------------------------------
    # Sentinel: signal all subscribers to shut down
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Push a ``None`` sentinel to every subscriber queue.

        Subscribers that receive ``None`` should stop iterating and
        clean up.  Called during server shutdown.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass
