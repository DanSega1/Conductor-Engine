---
name: memory-capability
description: In-memory key-value store capability for ephemeral data sharing between workflow steps. Supports get, set, delete, list, clear, and search.
mode: subagent
engine_ref: engine/capabilities/memory.py::MemoryCapability
events_ref: docs/guild/EDGE_EVENTS.md
risk_level: low
---

- Actions: get, set, delete, list, clear, search.
- set stores a value by key. get retrieves. delete removes. list enumerates. search filters by value pattern. clear wipes all.
- Data is in-memory only — not persisted across engine restarts.
- Useful for passing intermediate results between workflow steps within the same process.
