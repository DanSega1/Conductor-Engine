# Event Bus Agent

**Config:** `.opencode/agents/event-bus/event-bus.json`
**Engine ref:** `engine/interfaces/event.py::EventBus`
**Priority:** 9
**Role:** Fire-and-forget event emission for task lifecycle events.

## Purpose

The event bus emits structured `TaskEvent`s at every task lifecycle transition: started, completed, failed, retry, escalated, awaiting_approval, approved, cancelled, policy_denied. Emission is fire-and-forget — it must never block task execution or propagate exceptions. The `NullEventBus` is the default no-op implementation.

## Invariants

- emit() must never block task execution.
- emit() must never propagate exceptions to the task lifecycle. Catch and continue.
- `NullEventBus` is the default (minimal deployment emits nothing).
- `SSEEventBus` bridges sync supervisor threads to async SSE clients via `loop.call_soon_threadsafe`.

## Subagents

| Subagent | Engine ref | Behavior |
|---|---|---|
| null-event-bus | `engine/runtime/bus.py::NullEventBus` | No-op. emit() returns immediately. Default. |
| logging-event-bus | `engine/runtime/bus.py::LoggingEventBus` | Serializes events to structured JSON logs at INFO. |
| sse-event-bus | `engine/api/bus.py::SSEEventBus` | Bridges sync emits to async SSE streams. Holds subscription queues. |

## Event types

| EventType | Triggered by | Fields emitted |
|---|---|---|
| task_started | supervisor.run_task() | task_id, task_name, capability, status=RUNNING, attempt |
| task_completed | supervisor (on success) | task_id, capability, status=COMPLETED, attempt |
| task_failed | supervisor (on failure) | task_id, capability, status=FAILED, attempt, error |
| task_retry | supervisor (before retry) | task_id, capability, attempt, error, retry_reason |
| task_escalated | supervisor (max retries) | task_id, capability, status=ESCALATED, attempt, total_failures |
| task_awaiting_approval | supervisor (policy/descriptor) | task_id, capability, status=AWAITING_APPROVAL |
| task_approved | supervisor.approve_task() | task_id, capability, status=APPROVED, actor |
| task_cancelled | supervisor.cancel_task() | task_id, capability, status=CANCELLED, actor, error |
| task_policy_denied | supervisor._apply_policy() | task_id, capability, status=POLICY_DENIED, error, policy_engine |

## When to use

- null-event-bus: development, minimal deployments with no event consumers
- logging-event-bus: deployments that log events for post-hoc analysis
- sse-event-bus: when the control-plane API serves SSE streams to condor-tui or web clients
