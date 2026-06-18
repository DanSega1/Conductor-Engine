---
name: memory-store
description: In-memory dict-based TaskStore. No persistence across restarts. Used for tests and embedded runs only.
mode: subagent
engine_ref: engine/runtime/store.py::MemoryTaskStore
events_ref: docs/guild/EDGE_EVENTS.md
---

- Store all TaskRecords in a dict keyed by task_id.
- get() must return model_copy(deep=True) — callers must not mutate stored state.
- list() returns a shallow copy of matching records filtered by optional status.
- No serialization. No cross-process sharing. Ephemeral.
