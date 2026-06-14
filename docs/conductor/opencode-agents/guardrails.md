# Guardrails Agent

**Config:** `.opencode/agents/guardrails/guardrails.json`
**Engine ref:** `engine/guardrails/validation.py`
**Priority:** 7
**Role:** Validates task input schema and path safety before any task leaves PENDING.

## Purpose

Guardrails are the first gate in the supervisor execution path. `validate_task_submission()` is called twice per execution — once in `submit()` for early rejection, once in `run_task()` to resolve the capability reference. This duplication is intentional: the first call rejects invalid submissions before enqueueing, the second call resolves the concrete Capability object needed for execution.

## Invariants

- `validate_task_submission()` is the sole guardrail entry point. Custom guardrails are added here, not scattered in capability code.
- Called twice per execution (submit + run_task). This is intentional, not a bug.
- Path traversal protection: reject any path with `../` that escapes workdir.
- Return the resolved Capability object in the run_task() path.
- Guardrails are additive — they do not replace capability-level validate_input().

## Execution contract

```
validate_task_submission(submission: TaskSubmission, registry: CapabilityRegistry)
  → (early path) None — raises ValidationError on failure
  → (run_task path) Capability — returns the resolved capability instance
```

## Validation checks

1. Capability key exists in the registry
2. Required fields are present (name, capability)
3. Path parameters do not escape workdir (filesystem capability)
4. Input structure matches expected schema (basic type checks)

## When to use

- Before every task submission (called by supervisor automatically)
- When adding custom validation rules — extend here, not in capability code
- For safety-critical deployments where path traversal and input shape must be enforced at the platform level
