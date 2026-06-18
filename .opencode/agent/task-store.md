---
name: task-store
description: Persists TaskRecords at every state transition. Implements TaskStore Protocol. Always returns deep copies on reads. Multiple backend implementations available.
mode: subagent
engine_ref: engine/runtime/store.py::TaskStore
events_ref: docs/guild/EDGE_EVENTS.md
---

- save(task) — persist a TaskRecord. Called after every status transition.
- get(task_id) — return a deep copy of the TaskRecord, never the original reference.
- list(limit, offset, status) — paginated listing with optional status filter.
- Supports archive semantics — archived records are not hard-deleted.
- The TaskStore Protocol never changes — only implementations are swapped between phases.
