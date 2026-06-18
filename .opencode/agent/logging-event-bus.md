---
name: logging-event-bus
description: Logging event bus — writes all TaskEvents to structured logs via Python logging. Suitable for observability without a streaming consumer.
mode: subagent
engine_ref: engine/runtime/bus.py::LoggingEventBus
events_ref: docs/guild/EDGE_EVENTS.md
---

- Serialize TaskEvent to a structured log line (JSON format) at INFO level.
- Include all TaskEvent fields: event_type, task_id, task_name, capability, status, attempt, workflow_id, error, metadata.
- Must not raise exceptions on serialization failure — log a warning and continue.
