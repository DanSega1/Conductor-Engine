# Validator Agent

**Config:** `.opencode/agents/validator/validator.json`
**Engine ref:** `engine/interfaces/workflow.py::ValidatorInterface`
**Priority:** 4
**Role:** Assesses completed workflow results. Returns pass/fail verdict.

## Purpose

The validator receives the original `WorkflowGoal` and all completed `TaskRecord`s after execution. It returns a `ValidationResponse` with pass/fail status, a verdict string, and a list of issues. Validators never modify tasks, never re-run steps, and never call the supervisor.

## Invariants

- Does NOT modify tasks, re-run steps, or call the supervisor. Assesses only.
- If all TaskRecords are COMPLETED and the goal is satisfied, passed=true.
- If the goal is partially satisfied, passed=false with issues list.

## Subagents

| Subagent | Engine ref | Purpose |
|---|---|---|
| passthrough-validator | `engine/workflow/agents/passthrough_validator.py` | Always passes. Default stub for workflows without post-execution validation. |

## Execution contract

```
ValidatorContext(workflow_id, goal, results=[TaskRecord, ...])
  → validate(goal, context)
  → ValidationResponse(passed=True/False, verdict="...", issues=[...])
```

## Workflow result mapping

| Validator output | WorkflowStatus |
|---|---|
| passed=true | COMPLETED |
| passed=false | PARTIAL |

The verdict and issues appear in `WorkflowResult.verdict` and are surfaced in rich CLI output by `cond workflow run`.

## When to use

- After all workflow steps complete, before reporting the final result
- For domain-specific output validation (data quality, schema checks)
- As an extension point for AI-backed validation that inspects task outputs against the original goal
