# Workflow Orchestrator Agent

**Config:** `.opencode/agents/orchestrator/orchestrator.json`
**Engine ref:** `engine/workflow/orchestrator.py::WorkflowOrchestrator`
**Priority:** 1
**Role:** Coordinates planner → worker → supervisor → validator.

## Purpose

The orchestrator receives a `WorkflowGoal`, delegates to the planner for steps, farms each step out to the worker (which returns a `TaskSubmission`), executes each submission through the supervisor, and validates the final result. Pure orchestration — no business logic, no capability execution, no policy decisions.

## Invariants

- Calls `supervisor.run_submission()` — does NOT touch registry, store, or capabilities directly.
- Does NOT contain workflow logic (step sequencing, branching, goal tracking).
- Fail-fast on the first FAILED step in a batch.

## Delegation

```
orchestrator
├── planner      → plan(goal) → PlanResponse(steps)
├── worker       → work(step) → WorkerResponse(submission)
├── supervisor   → run_submission(submission) → TaskRecord
└── validator    → validate(goal, records) → ValidationResponse
```

## Execution flow

```
WorkflowGoal
  → planner.plan(goal, PlannerContext)
  → group steps into batches by parallel_group
  → for each batch:
      if single step: run synchronously
      if multi-step: ThreadPoolExecutor fan-out
      for each step:
        worker.work(step_name, WorkerContext)
        supervisor.run_submission(submission)
      if any FAILED: break (fail-fast)
  → validator.validate(goal, ValidatorContext)
  → WorkflowResult(status, records, verdict)
```

## parallel_group behavior

Steps with the same `parallel_group` value fan out concurrently. Sequential steps (no group) run one at a time. Example:

```yaml
steps:
  - name: fetch-users       # no group → runs first
    capability: http
  - name: fetch-orders      # group "data" → runs in parallel with fetch-products
    capability: http
    parallel_group: data
  - name: fetch-products    # group "data" → runs in parallel with fetch-orders
    capability: http
    parallel_group: data
  - name: generate-report   # no group → runs after both data tasks complete
    capability: filesystem
```

## Phases

Introduced in Phase 2. Synchronous in Phase 2, async with parallel steps added in Phase 3. The supervisor path underneath stays unchanged across all phases.
