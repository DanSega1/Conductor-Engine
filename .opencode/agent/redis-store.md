---
name: redis-store
description: Redis-backed TaskStore with persistent FIFO queue. Fast in-memory persistence with optional disk snapshotting. Phase 3+ backend.
mode: subagent
engine_ref: engine/runtime/store.py::RedisTaskStore
events_ref: docs/guild/EDGE_EVENTS.md
---

- Serialize TaskRecords as JSON strings in Redis hashes or JSON type.
- Use Redis sorted sets for paginated task listing by created_at.
- RedisQueue replaces InMemoryTaskQueue for persistent FIFO across restarts.
- Connection pooling and retry on connection failure.
