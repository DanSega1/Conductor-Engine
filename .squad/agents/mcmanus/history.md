# McManus — History

## Core Context

**Project:** Conductor-Engine — Python 3.12+ orchestration runtime (Pydantic v2, httpx, pyyaml)
**Owner:** Dan
**Role:** Backend Engine Dev

## Learnings

### 2026-03-31 — Retry logic added to supervisor
- Added `max_retries: int = 0` to `TaskSubmission` (submission-time config, not registry config)
- Added `attempt: int = 0` and `max_retries: int = 0` to `TaskRecord` so the store and tests can observe them
- `submit()` propagates `max_retries` from submission into the record
- `run_task()` uses a `while attempt <= max_retries` loop; on success it breaks out immediately; only the final exception is committed to `TaskResult`
- Default is 0 retries so all existing callers are unaffected
- Pattern: keep retry state on the record (observable), keep retry config on the submission (caller-controlled)

### 2026-03-31 — Project kickoff
- Phase 1 runtime is complete: `engine/supervisor/service.py` owns orchestration, `engine/registry/capabilities.py` handles registration and lookup
- Capability execution follows: validate input → execute → return `CapabilityResult` — the supervisor normalizes all results
- `engine/runtime/` contains the async queue (`queue.py`), JSON task store (`store.py`), and utilities (`async_utils.py`)
- Pydantic v2 models live in `engine/interfaces/` — these are the protocol contracts; don't break them
- Phase 2 agent roles are defined in `engine/interfaces/agent.py` but not wired into the runtime yet (`phase 1: no runtime dependency on agents`)
- Memory is behind an abstraction layer in `engine/memory/providers/memu.py` — optional dependency

### 2026-04-01 — Phase 2 Step 1: workflow contracts
- Created `engine/interfaces/workflow.py` — workflow-layer Pydantic v2 models and Protocol interfaces
- `WorkflowGoal` and `WorkflowResult` carry a `workflow_id` generated via `uuid4` `Field(default_factory=...)`
- `PlanStep.input_hint` is advisory (`dict[str, Any]`); the worker is responsible for refining it into a concrete `TaskSubmission`
- `WorkflowResult.verdict` is `ValidationResponse | None` — populated only when a validator has run; in-memory only (no store design yet)
- `WorkflowStatus` is a `StrEnum`: PENDING, RUNNING, COMPLETED, FAILED, PARTIAL
- Three Protocol pairs: `(PlannerContext, PlanResponse, PlannerInterface)`, `(WorkerContext, WorkerResponse, WorkerInterface)`, `(ValidatorContext, ValidationResponse, ValidatorInterface)`
- All protocols decorated with `@runtime_checkable` — consistent with `AgentInterface` in `agent.py`
- `agent.py` was NOT modified — `AgentContext`/`AgentResponse` remain in that file
- `engine/interfaces/__init__.py` updated to import and re-export all 13 new symbols in alphabetical `__all__`
- Import verified clean with `.venv12/bin/python`

### 2026-04-01 — Phase 2 Step 2: WorkflowOrchestrator
- Created `engine/workflow/__init__.py` (exports `WorkflowOrchestrator`) and `engine/workflow/orchestrator.py`
- `ValidatorInterface.validate` takes `(goal: str, context: ValidatorContext)` — not just `(context)`; always read the actual interface, not the task brief summary
- `ValidatorContext` uses `results: list[TaskRecord]` (not `records`); field names in brief task specs can diverge from source — always verify against `engine/interfaces/`
- `WorkflowResult.workflow_id` must be threaded from `goal.workflow_id`; the Pydantic default (`uuid4()`) would silently generate a new ID if not explicitly passed
- Fail-fast: check `record.status == TaskStatus.FAILED` after each supervisor call; break immediately and skip the validator
- No exception wrapping around supervisor calls — callers own error propagation
- Import verified clean with `.venv12/bin/python`

### 2026-04-01 — Phase 2 Step 3: stub agent implementations
- Created `engine/workflow/agents/` package with `LinearPlanner`, `PassthroughWorker`, `PassthroughValidator`
- `LinearPlanner` stores pre-built `PlanStep` list at construction; `plan()` returns them verbatim — goal/context are intentionally ignored
- `PassthroughWorker.work()` maps `context.step.capability` and `context.step.input_hint` directly into a `TaskSubmission`; step name becomes task name
- `PassthroughValidator.validate()` always returns `passed=True` — no logic, zero side effects
- All three satisfy their respective `@runtime_checkable` Protocol interfaces from `engine/interfaces/workflow.py`
- Import verified clean with `.venv12/bin/python`

### 2026-04-01 — Architecture review directives (post-Phase 2)
- **Archive-over-delete** applies to all store implementations (`LocalTaskStore`, `MemoryTaskStore`, and any future backend): records must never be hard-deleted; use `archived_at` or a cold-store move for all cleanup paths.
- **`workflow_id` must be added to `TaskRecord`** before Phase 3 — individual task records cannot be traced back to their originating workflow without it; this is a required field addition, not optional.
- **`ValidatorInterface` should be ABC, not Protocol** — `@runtime_checkable` Protocol `isinstance` checks confirm method name presence only, not signature match; switch to `ABC` + `abstractmethod` to enforce the full contract at class definition time.

### 2026-04-02 — Pre-Phase-3 model and interface fixes

- Extended `TaskStatus` with `AWAITING_APPROVAL`, `APPROVED`, `POLICY_DENIED`, `CANCELLED` to support policy and approval workflows.
- Added `AuditEntry` model to `engine/interfaces/task.py`; placed between `TaskResult` and `TaskRecord` to avoid forward-reference issues with the `list[AuditEntry]` field on `TaskRecord`.
- Added `workflow_id`, `archived_at`, and `audit_trail` to `TaskRecord`; new fields inserted after `max_retries`, before the `created_at`/`updated_at` bookends.
- Changed `ValidatorInterface` from `@runtime_checkable Protocol` to `ABC` with `@abstractmethod`; enforces the two-argument signature at class definition time. `PlannerInterface` and `WorkerInterface` remain as Protocols.
- `PassthroughValidator` now explicitly inherits `ValidatorInterface(ABC)` — required once the duck-typed Protocol was removed.
- Paginated `TaskStore.list()` across Protocol, `MemoryTaskStore`, and `LocalTaskStore`; keyword-only args (`limit`, `offset`, `status`) prevent positional misuse and keep filter/slice logic consistent between backends.
