# Fenster — History

## Core Context

**Project:** Conductor-Engine — Python 3.12+ orchestration runtime (Pydantic v2, httpx, pyyaml)
**Owner:** Dan
**Role:** Tester & QA

## Learnings

### 2026-03-31 — Project kickoff
- Test suite lives under `tests/engine/`: test_supervisor.py, test_cli.py, test_loader.py, test_memory.py
- `asyncio_mode = "auto"` in pyproject.toml — async tests don't need `@pytest.mark.asyncio`
- `pythonpath = ["."]` allows direct imports from engine/cli without install
- CI runs `pytest tests/engine -q` — all tests must pass for branch to merge
- Execution guarantees to test (per `docs/conductor/execution-flow.md`): input validated before task leaves pending, supervisor stores final TaskRecord regardless of success/failure
- Guardrail tests go in test_supervisor.py; capability-specific validation tests go alongside their capability

### 2026-04-01 — Workflow contracts test suite
- Created `tests/engine/test_workflow_contracts.py` ahead of `engine/interfaces/workflow.py` (contract-first testing)
- Covers: model construction, UUID uniqueness, advisory input_hint, records count, Protocol isinstance, WorkflowStatus enum, ValidationResponse defaults, Pydantic ValidationError on missing fields
- Ruff I001 (import block ordering) tripped on initial file — always run `ruff check --fix` to auto-sort imports
- `@runtime_checkable` Protocol isinstance checks require only method name presence, not signature match — inline mock classes suffice
- `WorkflowResult` and `WorkflowGoal` both use `uuid4` defaults; uniqueness test is a reliable way to assert this without mocking

### 2026-04-01 — WorkflowOrchestrator test suite (Phase 2, Step 2)
- Created `tests/engine/test_workflow_orchestrator.py` ahead of `engine/workflow/orchestrator.py` (contract-first, McManus builds impl)
- Used hand-written stub classes (`StubPlanner`, `CapturingWorker`, `CapturingValidator`, `FailingTaskSupervisor`) over pytest-mock — cleaner, Protocol conformance is explicit
- `TaskSupervisor.submit()` raises `ValueError` for unknown capabilities — it does NOT return a FAILED TaskRecord; failure-path tests require a stub supervisor returning a pre-built FAILED record
- `prior_results` accumulation is best verified by capturing the `WorkerContext` objects passed to each `work()` call, not by inspecting `WorkflowResult.records`
- Edge cases flagged for follow-up: zero-step plan, optional validator (None), exception from supervisor vs FAILED record

### 2026-04-01 — Stress/benchmark suite (test_stress.py)
- `CapabilityRegistry._capabilities` is the internal dict; `registry._capabilities["bomb"] = BombCapability()` is the correct injection point for test-only capabilities without touching the loader.
- Supervisor retry loop is `while task.attempt <= task.max_retries: task.attempt += 1`, so `max_retries=3` yields 4 total attempts and `task.attempt` ends at 4.  Safe assertion: `attempt >= 1`.
- `WorkflowOrchestrator` fail-fast: only 1 record is produced when the first step fails — do not assert `len(records) == N` for a failing workflow.
- `PassthroughWorker` injects `input_hint` verbatim as `TaskSubmission.input`; building a `ChainWorker` that reads `context.prior_results[-1].result.output` is the correct pattern for chained data flow tests.
- `MemoryTaskStore.list()` returns deep copies — isolation assertions must compare `task_id` sets, not object identity.
- Engine throughput is very high (~13 000 echo tasks/sec, 50-step workflow in ~4 ms avg). Benchmark thresholds (5 s for 1 000 tasks, 0.5 s per 50-step run) are conservative and should never regress under normal conditions.
- All 14 tests passed on first run without adjustment.

### 2026-04-01 — Architecture review carry-forwards (post-Phase 2)
- **`store.list()` loads all records** — stress tests revealed no pagination; when pagination is added, add a dedicated test asserting that `list()` respects page/limit parameters.
- **`archived_at` on `TaskRecord`** — once the field is added (archive-over-delete directive), update `test_stress.py` to assert that archived records carry a non-null `archived_at` timestamp.
- **`BombCapability` pattern is established** — injecting test-only capabilities via `registry._capabilities["name"] = CapabilityInstance()` is the accepted pattern for failure-simulation tests; reuse this in any future failure/chaos tests rather than introducing new injection mechanisms.
