# Session Log — 2026-04-01

**Phase:** 2 — Complete + Architecture Review

## What Happened

### Phase 2 Completion

All Phase 2 deliverables shipped and verified:

- **McManus** implemented `engine/workflow/orchestrator.py` (Step 2) and `engine/workflow/agents/` (Step 3): `LinearPlanner`, `PassthroughWorker`, `PassthroughValidator` stub implementations.
- **Fenster** wrote `tests/engine/test_workflow_orchestrator.py` (contract-first, hand-written stubs) and `tests/engine/test_stress.py` (14 stress/benchmark tests — all passed on first run; ~13 000 echo tasks/sec).
- **Hockney** added `cond workflow run` to `cli/cond.py` and created `try-it/workflow-echo.yaml` and `try-it/workflow-echo.py` integration examples.
- **McManus** (Step 1) delivered `engine/interfaces/workflow.py` with all workflow contracts (`WorkflowGoal`, `PlanStep`, `WorkflowResult`, `WorkflowStatus`, three Protocol interface pairs).

### Architecture Review Findings

The Coordinator identified 8 architectural flaws post-Phase 2:

1. **TaskRecord missing `workflow_id`** — records cannot be traced back to their originating workflow without it; must be added before Phase 3.
2. **`ValidatorInterface` is a Protocol, not ABC** — Protocol `isinstance` checks do not enforce method signatures; ABC is required for rigorous contract enforcement.
3. **`store.list()` loads all records** — no pagination; acceptable now but will become a bottleneck at scale; flagged for Phase 3.
4. **`TaskRecord` has no `archived_at` field** — required for the archive-over-delete directive; all softdelete/cleanup paths must write this field.
5. **`WorkflowResult` not persisted** — records are stored individually via the supervisor but assembled `WorkflowResult` objects are in-memory only; persistence deferred to Phase 3.
6. **No `workflow_id` propagation through `WorkerContext`** — workers lack the workflow identity at execution time; limits traceability.
7. **`BombCapability` pattern not formalized** — test-only capability injection via `registry._capabilities` is established but not documented in a test helper.
8. **Passthrough agents have no Phase 3 upgrade path defined** — stub agents will need replacement; interfaces are stable but wiring strategy for real agents is not yet decided.

### Key Directive Captured

- **Archive-over-delete** (Dan): Task records, workflow records, and all engine state must never be hard-deleted. All cleanup must use archival (`archived_at` field or cold-store move). Applies to all phases and all store backends.

## Decisions Recorded

- Archive-over-delete directive added to `decisions.md`
- All inbox decision files merged and cleared

## Next

Phase 3 planning — workflow persistence, `WorkflowResult` store, `workflow_id` propagation.
