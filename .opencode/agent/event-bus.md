---
name: event-bus
description: Fire-and-forget event emission system for task lifecycle events. Implements EventBus Protocol. Defaults to NullEventBus (no-op). Must never block task execution.
mode: subagent
engine_ref: engine/interfaces/event.py::EventBus
events_ref: docs/guild/EDGE_EVENTS.md
---

- emit(event_type, task_id, task_name, capability, status, attempt, workflow_id, error, metadata) -> None.
- Event emission must never block or propagate exceptions to the task lifecycle. If emit fails, silently catch and continue.
- Supported event types: task_started, task_completed, task_failed, task_retry, task_escalated, task_awaiting_approval, task_approved, task_cancelled, task_policy_denied.
- SSEEventBus bridges sync supervisor threads to async SSE clients via loop.call_soon_threadsafe.
- NullEventBus is the default — no-op for systems that don't consume events.
- LoggingEventBus writes events to structured logs for observability.
