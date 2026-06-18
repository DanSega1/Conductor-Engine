---
name: null-event-bus
description: No-op event bus — all emit() calls are silently discarded. Default when no event consumer is configured.
mode: subagent
engine_ref: engine/runtime/bus.py::NullEventBus
events_ref: docs/guild/EDGE_EVENTS.md
---

- emit() returns immediately without any action. No logging, no I/O, no side effects.
- This is the safe default for minimal deployments.
