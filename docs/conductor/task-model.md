# Task Model

## Purpose

The Phase 1 engine uses a minimal task document that is independent of Home AI Control Plane concerns like Notion, Mongo, OPA, or planner outputs.

## Models

### `TaskSubmission`

Input accepted by the runtime or CLI:

```yaml
name: Save hello.txt
capability: filesystem
input:
  action: write_text
  path: notes/hello.txt
  content: hello
max_retries: 2
metadata:
  source: cli
```

Fields:

- `name`: human-readable task title
- `capability`: registry key to execute
- `input`: capability-specific payload
- `max_retries`: optional retry count on capability failure (default: `0`)
- `metadata`: optional caller context

### `TaskRecord`

Persisted task state:

- `task_id`
- `name`
- `capability`
- `input`
- `metadata`
- `status`
- `result`
- `attempt` — number of execution attempts made (incremented per retry)
- `max_retries` — retry budget copied from the submission
- `created_at`
- `updated_at`

### `TaskStatus`

State machine:

```text
Pending -> Running -> Completed / Failed
```

## Design Notes

- The task model is execution-first and planner-free for `v0.1`.
- Capability inputs remain opaque to the core runtime and are validated by the selected capability.
- The model is small enough to store in memory or a local JSON file while still being portable to Postgres or Mongo later.
