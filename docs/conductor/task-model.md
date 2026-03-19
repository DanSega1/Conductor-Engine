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
metadata:
  source: cli
```

Fields:

- `name`: human-readable task title
- `capability`: registry key to execute
- `input`: capability-specific payload
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
