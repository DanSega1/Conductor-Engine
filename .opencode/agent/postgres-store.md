---
name: postgres-store
description: PostgreSQL-backed TaskStore. Production-grade persistence for multi-node deployments. Full ACID compliance. Phase 3+ backend.
mode: subagent
engine_ref: engine/runtime/store.py::PostgresTaskStore
events_ref: docs/guild/EDGE_EVENTS.md
---

- Map TaskRecord fields to a PostgreSQL table with JSONB for audit_trail and dynamic fields.
- Use parameterized queries for all operations. No raw string interpolation.
- save() performs an UPSERT on conflict(task_id).
- list() uses SQL LIMIT/OFFSET and WHERE status filter.
