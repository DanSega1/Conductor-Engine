"""Server-Sent Events (SSE) route for real-time task lifecycle streaming.

Endpoints
---------
GET  /v1/events    Live event stream (text/event-stream)

Query parameters
----------------
types : comma-separated list of event types to include.
        When omitted, all event types are forwarded.
        Example: ``?types=task_completed,task_failed``

Event format
------------
Each event is a standard SSE frame::

    event: task_completed
    data: {"event_type":"task_completed","task_id":"...","task_name":"...","status":"completed",...}

A heartbeat comment is sent every 15 seconds when no events occur::

    : heartbeat

Consumers
---------
- condor-tui: subscribes on launch, drives the live task queue panel.
- Wrapper services: subscribe to react to task_failed / task_escalated.
- Web UI (Phase 4+): drives live dashboards.
- MCP layer (future): may forward events as tool call notifications.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from engine.api.bus import SSEEventBus
from engine.api.dependencies import EventBusDep

router = APIRouter(tags=["events"])

_HEARTBEAT_INTERVAL = 15.0  # seconds between keep-alive pings


async def _event_generator(
    bus: SSEEventBus,
    type_filter: frozenset[str] | None,
) -> AsyncGenerator[str, None]:
    """Async generator that streams SSE frames to one client."""
    queue = bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_INTERVAL)
            except TimeoutError:
                # Keep the connection alive with a comment line.
                yield ": heartbeat\n\n"
                continue

            # None sentinel means the bus is shutting down.
            if event is None:
                break

            if type_filter is not None and event.event_type.value not in type_filter:
                continue

            yield f"event: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"
    finally:
        bus.unsubscribe(queue)


@router.get(
    "/events",
    summary="Live event stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events stream",
            "content": {"text/event-stream": {}},
        },
        503: {"description": "SSE not configured on this server"},
    },
)
async def stream_events(
    bus: EventBusDep,
    types: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated event type filter. "
                "Example: task_completed,task_failed,task_escalated"
            )
        ),
    ] = None,
):
    """Subscribe to a live stream of task lifecycle events.

    Events are pushed as Server-Sent Events (SSE) — compatible with the
    browser ``EventSource`` API, ``curl``, and any SSE client library.

    **Supported event types:**
    - ``task_started``
    - ``task_completed``
    - ``task_failed``
    - ``task_retry``
    - ``task_policy_denied``
    - ``task_awaiting_approval``
    - ``task_approved``
    - ``task_cancelled``
    - ``task_escalated``

    **Example (curl):**
    ```bash
    curl -N http://localhost:8080/v1/events
    curl -N "http://localhost:8080/v1/events?types=task_completed,task_failed"
    ```

    **Example event frame:**
    ```
    event: task_completed
    data: {"event_type":"task_completed","task_id":"abc123","task_name":"Echo hello","status":"completed","attempt":1}
    ```
    """
    type_filter: frozenset[str] | None = None
    if types:
        type_filter = frozenset(t.strip() for t in types.split(",") if t.strip())

    return StreamingResponse(
        _event_generator(bus, type_filter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
