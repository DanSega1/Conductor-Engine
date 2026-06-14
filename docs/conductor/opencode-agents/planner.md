# Planner Agent

**Config:** `.opencode/agents/planner/planner.json`
**Engine ref:** `engine/interfaces/workflow.py::PlannerInterface`
**Priority:** 2
**Role:** Breaks workflow goals into ordered PlanSteps. Never executes.

## Purpose

The planner receives a `WorkflowGoal` (goal string + available capabilities) and returns a `PlanResponse` with an ordered list of `PlanStep`s. Each step names a capability and provides advisory `input_hint`. The planner never calls the supervisor, never executes capabilities — it plans only.

## Invariants

- Does NOT execute any step. Planners plan only.
- Each PlanStep references a capability that exists in the registry.
- `input_hint` is advisory — the worker refines it into a concrete TaskSubmission.
- `parallel_group` marks adjacent steps for concurrent fan-out.
- A `rationale` string explains the plan structure.

## Subagents

| Subagent | Purpose |
|---|---|
| linear-planner | Deterministic ordered-step planner from structured goals. Stub for extension. |

## Execution contract

```
PlannerContext(workflow_id, goal, capabilities)
  → plan(goal, context)
  → PlanResponse(steps=[PlanStep(...), ...], rationale="...")
```

## When to use

- Before any multi-step workflow execution
- When a goal needs decomposition into capability calls
- For orchestration that chains multiple tasks together

## Extending

The linear-planner subagent is a stub. Override with an LLM-backed planner by implementing the `PlannerInterface` protocol externally and swapping the subagent config.
