# Supervisor Agent

**Config:** `.opencode/agents/supervisor/supervisor.json`
**Engine ref:** `engine/supervisor/service.py::TaskSupervisor`
**Priority:** 0 (primary agent)
**Role:** Top-level orchestrator. The only path through which capabilities execute.

## Purpose

The supervisor agent mirrors `TaskSupervisor` — it validates every `TaskSubmission`, resolves the target capability, enforces policy, executes through the capability, persists every state transition, and handles retry/escalation. No agent or orchestrator calls a capability directly; all execution goes through this agent.

## Invariants encoded

| Invariant | Guard |
|---|---|
| Supervisor is the only execution path | Instructions forbid direct capability calls from any other agent |
| Guardrails before PENDING | validate_task_submission() is the first gate |
| State persisted at every transition | store.save() before and after every status change |
| ESCALATED is terminal | Once ESCALATED written, no transition back to RUNNING |
| EventBus fire-and-forget | emit() must never block or propagate exceptions |
| Store reads return deep copies | get() returns model_copy(deep=True) |

## Delegation

```
supervisor
├── capability-registry   → resolve capability by name, get execution controls
├── guardrails            → validate_task_submission() early + late
├── policy-engine         → evaluate(task) → ALLOW/DENY/REQUIRE_APPROVAL
├── task-store             → save() at every transition, get() for reads
├── event-bus              → emit() lifecycle events (fire-and-forget)
└── workflow-orchestrator  → for workflow goals (not direct delegation, but supervisor-top-level)
```

## Subagents

| Subagent | Purpose |
|---|---|
| default-retry | Simple attempt cap with escalation threshold |
| exponential-backoff-retry | 2^n delay for transient failures |
| jittered-backoff-retry | Backoff + random jitter to avoid thundering herd |
| input-adjusting-retry | Modifies input per retry attempt |
| subprocess-runner | Isolated child-process execution with hard timeout |

## Execution flow

```
TaskSubmission
  → validate_task_submission()        (guardrails)
  → require_approval flag check        (capability descriptor)
  → policy_engine.evaluate()           (ALLOW / DENY / REQUIRE_APPROVAL)
  → execution controls check           (timeout, min_interval)
  → capability.validate_input()
  → capability.execute()
  → store.save(COMPLETED / FAILED)
  → event_bus.emit(task_completed / task_failed)
```

On failure:
```
  → build FailureContext
  → append audit entry
  → retry_strategy.decide()
  → if should_retry: delay + retry
  → if escalate: transition to ESCALATED (terminal)
  → else: store.save(FAILED)
```

## When to use

- Submitting a single task (`cond run`)
- Executing a capability directly
- Any operation that touches a capability
- Approval gates and task lifecycle management
