# Conductor Engine — Design Integrity

A living document tracking cross-phase invariants, confirmed architectural rules, and known gaps.

Update this document whenever a phase completes, a gap is closed, or a new invariant is established.

Last reviewed: 2026-05-01 (Phase 5 Slice 2 complete)

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
| 8 | Failure context must be durable and observable | `FailureContext` persisted in `TaskRecord.audit_trail` before retry decisions (Phase 5) |
| 9 | ESCALATED is a terminal status — the supervisor must never transition an ESCALATED task back to RUNNING | `engine/supervisor/service.py` — once `TaskStatus.ESCALATED` is written to the store, no subsequent state machine transition may overwrite it with RUNNING |

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

No Phase 3 integrity gaps are currently open in the core runtime.

The remaining constraints are explicit design boundaries, not accidental holes:

- **Timeouts are soft in the in-process runtime.** The supervisor can fail a task after a configured timeout, but it cannot forcibly terminate arbitrary in-flight work without moving capability execution into an isolated process.
- **Parallelism is grouped, not DAG-based.** Adjacent steps that share `parallel_group` fan out concurrently, then synchronize before later steps. Full dependency graphs remain deferred.
- **MCP transport is addon-owned.** Core provides an `MCPCapability` seam, but connection/session management lives in `conductor-mcp` rather than the base package.

---

## Closed Gaps

| ID | Description | Resolved in |
|----|-------------|-------------|
| — | Store Protocol defined; MemoryTaskStore and LocalTaskStore implemented | Phase 1 |
| — | Workflow contracts defined before orchestrator was built | Phase 2 Step 1 |
| — | ValidatorInterface promoted to ABC (was duck-typed Protocol) | Phase 3 |
| G1 | Supervisor writes `audit_trail` entries for transitions and retries | Phase 3 |
| G2 | Extended `TaskStatus` values are reachable through policy and approval flows | Phase 3 |
| G3 | Workflow submissions propagate `workflow_id` into stored task records | Phase 3 |
| G4 | `supervisor.list_tasks()` exposes pagination and status filtering | Phase 3 |
| G5 | `run_coro()` is safe inside active event loops without adding async public APIs | Phase 3 |
| G6 | Retry attempts emit `TASK_RETRY` events and append audit entries | Phase 3 |

---

## Decisions to Preserve

These decisions must not be quietly reversed by future changes.

- **No in-memory-only critical state.** MemoryTaskStore is for tests and embedded runs only. Production paths route through a persisted store.
- **EventBus is fire-and-forget.** `emit()` must not block task execution. Slow or failing event emission must not propagate exceptions to the task lifecycle.
- **Capabilities validate their own inputs.** `capability.validate_input()` is called before `capability.execute()`. Guardrails at the submission boundary are additive, not a replacement.
- **Null objects over None checks.** `NullEventBus`, `PassthroughValidator` — new optional components introduce a null implementation rather than sprinkling `if x is not None` checks through the supervisor.
- **Execution controls live outside task input.** Timeouts and rate limits are runtime-configured per capability, not part of `TaskSubmission`.
- **Parallel workflow batches are explicit barriers.** `parallel_group` enables controlled fan-out without turning the Phase 2 workflow contract into a full DAG scheduler.
- **Soft timeouts must stay honest.** The current runtime may mark a task failed after a timeout, but it must not pretend that arbitrary user code was forcibly terminated.
