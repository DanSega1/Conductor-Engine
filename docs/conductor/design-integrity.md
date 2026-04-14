# Conductor Engine — Design Integrity

A living document tracking cross-phase invariants, confirmed architectural rules, and known gaps.

Update this document whenever a phase completes, a gap is closed, or a new invariant is established.

Last reviewed: 2026-04-08 (Phase 3 in progress, post-Phase 2 checkup)

---

## Non-Negotiable Invariants

These must hold at every phase. Breaking any of them is a regression, not a tradeoff.

| # | Invariant | Where enforced |
|---|-----------|----------------|
| 1 | The supervisor is the only path through which a capability executes | `engine/supervisor/service.py` — no capability is called from orchestrators or agents directly |
| 2 | Guardrails run before a task leaves PENDING | `validate_task_submission()` called in `supervisor.submit()` and `supervisor.run_task()` |
| 3 | Task state is persisted at every transition | `store.save(task)` called after PENDING, RUNNING, and terminal states in `run_task()` |
| 4 | Capabilities are stateless | `Capability.execute()` receives isolated `CapabilityContext` per call; no shared mutable state on the instance |
| 5 | Path traversal is rejected at the filesystem boundary | `ensure_local_path()` in `guardrails/validation.py` rejects paths escaping `workdir` |
| 6 | The EventBus is injected, never hardcoded | Supervisor accepts `event_bus: EventBus | None`; defaults to `NullEventBus` |
| 7 | Store reads return deep copies | `MemoryTaskStore` uses `model_copy(deep=True)` — callers cannot mutate stored state by accident |

---

## Phase Contract Boundaries

### Supervisor ↔ Orchestrator

- The orchestrator calls `supervisor.run_submission()` — it does not touch the registry, store, or capabilities directly.
- The supervisor does not contain workflow logic (step sequencing, branching, goal tracking).
- If this boundary breaks, retry logic, audit trail, and event emission stop working for workflow steps.

### Supervisor ↔ Guardrails

- `validate_task_submission()` is the sole guardrail entry point. Custom guardrails must be added here, not scattered in capability code.
- `validate_task_submission()` is deliberately called twice per execution (once in `submit()`, once in `run_task()`): the first call validates and rejects early; the second call resolves the `Capability` reference needed for execution. This is intentional duplication, not a bug.

### TaskRecord ↔ TaskSubmission

- `TaskSubmission` is the input contract; `TaskRecord` is the stored artifact. They are separate models by design.
- `TaskRecord` should have more fields than `TaskSubmission` (audit trail, timestamps, attempt counter, workflow linkage). Never collapse them.

---

## Known Gaps (open)

These are real gaps in the current implementation. Each one has a resolution path listed under Phase 3 Remaining in `roadmap.md`.

### G1 — `audit_trail` is never written

**File:** `engine/supervisor/service.py`

`TaskRecord.audit_trail` and `AuditEntry` are modelled correctly but the supervisor never appends entries during state transitions. The field is always `[]`.

Every status transition in `run_task()` should append an `AuditEntry` (actor: `"supervisor"`, from/to status, timestamp). Retry attempts should produce entries too.

**Resolution:** Part of the audit trail work; add `_append_audit()` helper in the supervisor before Phase 3 is marked complete.

### G2 — Extended `TaskStatus` values are unreachable

**File:** `engine/interfaces/task.py`

`AWAITING_APPROVAL`, `APPROVED`, `POLICY_DENIED`, and `CANCELLED` are defined on `TaskStatus` but nothing in the runtime transitions to them. They are declared but orphaned.

**Resolution:** The `PolicyEngine` interface (Phase 3 Remaining) will create the transition path for `POLICY_DENIED`. Approval flows create `AWAITING_APPROVAL` → `APPROVED`. Until those land, these states are forward-reserved only.

### G3 — `workflow_id` is never set on `TaskRecord` during workflow execution

**File:** `engine/workflow/orchestrator.py`, `engine/interfaces/task.py`

`TaskSubmission` has no `workflow_id` field. When the orchestrator calls `supervisor.run_submission()` for a workflow step, the resulting `TaskRecord.workflow_id` is always `None`. You cannot query the store for "all tasks belonging to workflow X".

**Resolution:** Add `workflow_id: str | None = None` to `TaskSubmission`. The orchestrator sets it when constructing submissions from `WorkerResponse`. The supervisor propagates it to the `TaskRecord`.

### G4 — `supervisor.list_tasks()` ignores pagination

**File:** `engine/supervisor/service.py`

`TaskStore.list()` accepts `limit`, `offset`, and `status` parameters. `supervisor.list_tasks()` calls `store.list()` with no arguments — the new pagination capability is not exposed at the supervisor API.

**Resolution:** Add `limit`, `offset`, `status` parameters to `list_tasks()` and pass them through.

### G5 — `async_utils.run_coro` fails inside async contexts

**File:** `engine/runtime/async_utils.py`

`run_coro()` raises `RuntimeError` if called from a running event loop. This makes async memory providers unusable from within an async host. The current sync-only execution model hits this wall when any caller has an event loop active.

**Resolution:** Phase 3 remaining item: replace `async_utils.py` with a proper async execution path design. Until then, `run_coro` is explicitly not safe in async hosts.

### G6 — Retry attempts emit no per-attempt events

**File:** `engine/supervisor/service.py`

The retry loop runs silently. Only `task_started` and the final `task_completed` or `task_failed` events are emitted. Individual retry attempts are invisible to the event stream and the audit trail.

**Resolution:** Emit a `task_retry` event (or add a `TASK_RETRY` event type) at the start of each retry attempt. Also append an `AuditEntry` per retry (depends on G1 being fixed).

---

## Closed Gaps

| ID | Description | Resolved in |
|----|-------------|-------------|
| — | Store Protocol defined; MemoryTaskStore and LocalTaskStore implemented | Phase 1 |
| — | Workflow contracts defined before orchestrator was built | Phase 2 Step 1 |
| — | ValidatorInterface promoted to ABC (was duck-typed Protocol) | Phase 3 |

---

## Decisions to Preserve

These decisions must not be quietly reversed by future changes.

- **No in-memory-only critical state.** MemoryTaskStore is for tests and embedded runs only. Production paths route through a persisted store.
- **EventBus is fire-and-forget.** `emit()` must not block task execution. Slow or failing event emission must not propagate exceptions to the task lifecycle.
- **Capabilities validate their own inputs.** `capability.validate_input()` is called before `capability.execute()`. Guardrails at the submission boundary are additive, not a replacement.
- **Null objects over None checks.** `NullEventBus`, `PassthroughValidator` — new optional components introduce a null implementation rather than sprinkling `if x is not None` checks through the supervisor.
