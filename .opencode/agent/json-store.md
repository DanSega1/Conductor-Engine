---
name: json-store
description: File-based local JSON TaskStore. Persists all TaskRecords to a JSON file on disk. Suitable for single-node deployments.
mode: subagent
engine_ref: engine/runtime/store.py::LocalTaskStore
events_ref: docs/guild/EDGE_EVENTS.md
---

- Serialize all TaskRecords to a JSON file at a configurable path.
- Load from file on init, flush to file on every save().
- get() returns deep_copy(model_copy(deep=True)).
- list() filters by optional status and paginates with limit/offset.
