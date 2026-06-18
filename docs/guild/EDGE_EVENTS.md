# Edge Events — Shared Agent Event Catalog

All Conductor Engine agents share awareness of these lifecycle events.
Every `agents.md` or agent profile can reference this file so all roles
speak the same event vocabulary.

Events are fire-and-forget — they never block task execution.

---

## Task Lifecycle Events

| Event | Fires When | Carries | Agents That Should Care |
|---|---|---|---|
| `task_started` | A task moves from PENDING/APPROVED → RUNNING | task_id, capability, attempt, max_retries | supervisor, worker, planner |
| `task_completed` | A capability executes successfully | task_id, capability, attempt, output summary | supervisor, worker, validator, planner |
| `task_failed` | A capability raises and retries are exhausted | task_id, capability, attempt, error message | supervisor, worker, planner, guild |
| `task_retry` | A retry strategy decides to retry after failure | task_id, capability, attempt, delay, adjusted_input | supervisor, worker |
| `task_escalated` | Retry+escalation policy decides human intervention needed | task_id, capability, failure_history, reason | supervisor, guild, planner |
| `task_policy_denied` | A policy engine denies execution | task_id, capability, policy_engine, reason | supervisor, policy-engine, planner |
| `task_awaiting_approval` | A task pauses for human approval | task_id, capability, reason (require_approval or policy) | supervisor, planner, human |
| `task_approved` | A human or automation approves a paused task | task_id, actor, metadata | supervisor, planner |
| `task_cancelled` | A paused task is cancelled by a human | task_id, actor, reason | supervisor, planner |
| `guild_meeting_completed` | A guild meeting finishes consolidating knowledge | meeting_id, roles_present, total_records, summary | guild, all roles |

---

## Event Data Shape

Every event carries a `TaskEvent` envelope:

```
event_type    — which event (see table above)
task_id       — the task that triggered it
task_name     — human-readable task name
capability    — which capability was being used
status        — the task's new status after the transition
attempt       — current attempt number
timestamp     — when the event was emitted (UTC ISO-8601)
workflow_id   — optional, if the task is part of a workflow
error         — optional, error message for failure events
metadata      — optional, additional context key-value pairs
```

---

## How Agents Use Events

| Role | Consumes | Produces |
|---|---|---|
| **Supervisor** | — (is the source) | All task events |
| **Planner** | task_completed, task_failed, task_escalated | PlanResponse |
| **Worker** | task_started, task_completed, task_failed | TaskSubmission |
| **Validator** | task_completed | ValidationResponse |
| **Guild** | task_failed, task_escalated, task_completed | GuildRecord, peer suggestions |
| **Policy Engine** | — (evaluates before events fire) | PolicyDecision |

---

## Event Bus Implementations

| Bus | Behavior | Use Case |
|---|---|---|
| `NullEventBus` | Discards all events silently | Default — no consumer needed |
| `LoggingEventBus` | Writes events to structured logs | Observability without streaming |
| `SSEEventBus` | Bridges sync threads → async SSE clients | Control-plane API / TUI |

---

## Agent Convention

All agent `.md` files should include a line like this in their frontmatter or body:

```
events_ref: docs/guild/EDGE_EVENTS.md
```

This ensures every agent profile is linked to the same canonical event
vocabulary. When new events are added, update this file and all agents
automatically stay in sync through the reference.
