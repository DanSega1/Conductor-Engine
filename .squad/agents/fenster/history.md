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

### 2026-04-14 — Release notes QA review
- QA'd Kobayashi's implementation of "Release notes on GitHub releases" roadmap backlog item
- **Critical defect found and fixed:** Template used `{{ repo }}` but PSR v10 provides `{{ owner }}` and `{{ repo_name }}` as separate variables
- Validated semantic-release config keys against PSR v10.5.3 spec: `upload_to_release`, `template_dir`, `changelog.default_templates.release_body` all valid
- Template Jinja2 syntax validation: checked if/endif pairing, balanced braces, variable references
- Template fallback handling: `{% if changelog %}...{% else %}No changes recorded.{% endif %}` prevents empty release bodies
- Roadmap status date (2026-04-14) matches current session date — consistency check passed
- No new test failures or lint issues introduced; pre-existing CLI test failures are unrelated (package not installed in dev mode)
- **Learning:** python-semantic-release v10 template context provides `owner`, `repo_name`, `version`, `changelog` (NOT `repo` as a combined string)
- **Pattern:** For PSR release templates, always use `{{ owner }}/{{ repo_name }}` for GitHub URLs, never assume a combined `{{ repo }}` variable exists

### 2026-05-01 — Phase 5 Slice 2: Escalation Paths Test Suite

- Created `tests/engine/test_escalation.py` ahead of McManus's implementation (spec-first testing per squad workflow)
- **Scope:** 20 tests covering `EscalationConfig`, `EscalationRecord`, `ThresholdEscalationPolicy`, and supervisor integration
- Tests import from `engine.interfaces.escalation` and `engine.runtime.escalation` (contracts not yet implemented by McManus)
- **Current status:** 19 tests fail with `ModuleNotFoundError`, 1 regression guard passes (task without policy → FAILED, not ESCALATED)
- **Coverage areas:**
  - `EscalationConfig` Pydantic model: construction, defaults, validation on missing required field
  - `EscalationRecord` Pydantic model: construction, optional fields, full round-trip serialization (`.model_dump()` → reconstruct)
  - `ThresholdEscalationPolicy.should_escalate`: below/at/above threshold logic
  - `ThresholdEscalationPolicy.build_record`: history population, timestamps, config reason vs default reason
  - Supervisor integration: task status → ESCALATED, `EscalationRecord` stored in `task.result.metadata`, audit trail contains "escalated" entry, `TASK_ESCALATED` event emitted exactly once
  - Regression guard: task without `EscalationPolicy` still transitions to FAILED when retries exhausted
  - Normal retry flow preserved: task below escalation threshold retries normally
- **Test helper pattern:** Used existing supervisor test helper (MemoryTaskStore, CapturingEventBus, FailingCapability inline classes) from `test_supervisor.py`
- **Pattern learned:** When writing tests for parallel implementation, one regression guard test validates that absence of new feature preserves old behavior — this test passes immediately and confirms non-interference
- **Coordination:** Tests will be run together with McManus's implementation after both finish; failures expected until modules exist
