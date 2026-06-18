---
name: sse-event-bus
description: Server-Sent Events bridge — sync supervisor threads emit events to async SSE clients via loop.call_soon_threadsafe.
mode: subagent
engine_ref: engine/api/bus.py::SSEEventBus
events_ref: docs/guild/EDGE_EVENTS.md
---

- Bridge sync supervisor emit() calls to async SSE event streams.
- Use loop.call_soon_threadsafe to enqueue events from supervisor threads to the asyncio event loop.
- Support type-filtered subscriptions (filter by EventType per connection).
- Hold a set of active SSE subscription queues. Clean up disconnected clients.
- Must not block or raise — fire-and-forget contract applies.
