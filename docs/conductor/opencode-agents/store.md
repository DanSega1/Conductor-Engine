# Task Store Agent

**Config:** `.opencode/agents/store/store.json`
**Engine ref:** `engine/runtime/store.py::TaskStore`
**Priority:** 8
**Role:** Persists TaskRecords at every state transition. Deep-copy reads.

## Purpose

The task store persists `TaskRecord`s at every lifecycle transition. `save()` is called after PENDING, RUNNING, and every terminal state. `get()` always returns a deep copy — callers cannot mutate stored state by accident. The `TaskStore` Protocol never changes; only implementations are swapped across phases.

## Invariants

- save() called after every status transition (PENDING, RUNNING, COMPLETED, FAILED, POLICY_DENIED, AWAITING_APPROVAL, APPROVED, CANCELLED, ESCALATED).
- get() returns `model_copy(deep=True)` — never the original reference.
- list() supports pagination (limit, offset) and optional status filter.
- Archive semantics: archived records are not hard-deleted.
- The Protocol never changes — only implementations are swapped.

## Subagents

| Subagent | Engine ref | Persistence | Use case |
|---|---|---|---|
| memory-store | `engine/runtime/store.py::MemoryTaskStore` | None (RAM only) | Tests, embedded runs |
| json-store | `engine/runtime/store.py::LocalTaskStore` | JSON file on disk | Single-node, local dev |
| postgres-store | `engine/runtime/store.py::PostgresTaskStore` | PostgreSQL | Production, multi-node, ACID |
| redis-store | `engine/runtime/store.py::RedisTaskStore` | Redis + optional snapshot | Fast in-memory, persistent queue |

## Protocol

```
save(task: TaskRecord)                    → None          # persist at every transition
get(task_id: str)                         → TaskRecord     # deep copy
list(limit, offset, status)               → list[TaskRecord]  # paginated
```

## Phase progression

```
Phase 1: memory-store, json-store
Phase 3: postgres-store, redis-store (add, don't replace)
InMemoryTaskQueue → RedisQueue (persistent FIFO in Phase 3)
```

## When to use

- After every task state transition (called by supervisor automatically)
- memory-store: unit tests, development smoke tests
- json-store: local single-node deployments, `cond run` without a database
- postgres-store: production deployments requiring ACID guarantees
- redis-store: high-throughput deployments needing fast in-memory access with persistence
