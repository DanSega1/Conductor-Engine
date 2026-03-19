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

## Deferred To Later Phases

- Planning
- Multi-step workflows
- Policy engines
- Approval flows
- Distributed queues
- Retries and iteration control
