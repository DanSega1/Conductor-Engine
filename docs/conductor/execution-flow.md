# Execution Flow

## Phase 1

The initial runtime is intentionally simple:

```text
Task file or API request
  -> Supervisor
  -> Capability Registry lookup
  -> Capability input validation
  -> Capability execution
  -> Result persisted to TaskStore
```

## Sequence

1. Caller submits a `TaskSubmission`
2. Supervisor validates the task and enqueues it
3. Supervisor resolves the target capability from the registry
4. Capability validates its own input schema
5. Capability executes and returns a normalized result
6. Supervisor stores a final `TaskRecord`

## Retry Behaviour

Retry is part of the Phase 1 runtime. Set `max_retries` on a `TaskSubmission` to retry on capability failure:

```text
Capability raises exception
  -> attempt incremented
  -> if attempt <= max_retries: retry
  -> else: TaskRecord stored as FAILED with error and final attempt count
```

`TaskRecord.attempt` and `TaskRecord.max_retries` are persisted so callers can inspect how many attempts were made.

Default is `max_retries=0` — one attempt, no retries. Existing callers are unaffected.

## Deferred To Later Phases

- Planning (Phase 2)
- Multi-step workflows (Phase 2)
- Policy engines (Phase 3)
- Approval flows (Phase 3)
- Distributed queues (Phase 7)
- Iteration control and adaptive retry (Phase 5)
