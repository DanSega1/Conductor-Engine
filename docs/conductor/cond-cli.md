# cond CLI

`cond` is the command-line interface for Conductor Engine. It lets you run tasks, inspect capabilities, and review task history from a terminal.

## Installation

```bash
pip install -e .
```

## Commands

### `cond run <task-file>`

Execute a task defined in a YAML or JSON file.

```bash
cond run task.yaml
```

**Output:**
```
╭─ Echo smoke test ──────────────────────╮
│ status      ✓ completed                │
│ capability  echo                       │
│ attempts    1                          │
│ output      {"message":"hello from…"}  │
╰────────────────────────────────────────╯
```

On failure the border turns red and shows an `error` row instead of `output`.

---

### `cond capability list`

List all capabilities registered in the engine.

```bash
cond capability list
```

**Output:**
```
 Name        Risk    Tags
 echo        low     testing, utility
 filesystem  medium  io, local
 http        medium  network, api
```

---

### `cond task list`

Show all tasks recorded in the local store (`.conductor/tasks.json`).

```bash
cond task list
```

**Output:**
```
 ID         Name              Status     Capability  Attempts
 6ebe9f69…  Echo smoke test   completed  echo        1
 4ed6f5e8…  Retry on failure  failed     http        3 / 3
```

---

### `cond help [topic]`

Show offline reference pages for commands and capabilities.

```bash
man cond
cond help
cond help echo
cond help workflow
```

Use `man cond` for the stable CLI reference. Use `cond help` for runtime-aware topics such as loaded capabilities. Standard CLI usage help still works with `cond -h` and `cond --help`.

---

## Global flags

| Flag | Default | Description |
|------|---------|-------------|
| `--store <path>` | `.conductor/tasks.json` | Path to the local task store |
| `--config <path>` | `config/conductor.capabilities.yaml` | Path to capability config YAML |

---

## Task file format

```yaml
name: My task          # human-readable title
capability: echo       # which capability to execute
input:                 # capability-specific payload
  message: hello
max_retries: 0         # optional — retry on failure (default: 0)
metadata:              # optional caller context
  source: cli
```

---

## Examples

### Echo — smoke test

```yaml
name: Echo smoke test
capability: echo
input:
  message: hello from conductor
```

```bash
cond run examples/echo.yaml
```

---

### Filesystem — write a file

```yaml
name: Write a note
capability: filesystem
input:
  action: write_text
  path: notes/hello.txt
  content: "hello from conductor engine"
```

```bash
cond run examples/write-file.yaml
```

Supported `action` values: `write_text`, `read_text`, `list_dir`.

---

### Filesystem — read a file

```yaml
name: Read the note back
capability: filesystem
input:
  action: read_text
  path: notes/hello.txt
```

---

### Filesystem — list a directory

```yaml
name: List notes
capability: filesystem
input:
  action: list_dir
  path: notes
```

---

### HTTP — outbound GET request

```yaml
name: Fetch status
capability: http
input:
  method: GET
  url: https://httpbin.org/get
```

---

### HTTP — POST with body

```yaml
name: Post data
capability: http
input:
  method: POST
  url: https://httpbin.org/post
  body:
    key: value
```

---

### Retry on transient failure

Add `max_retries` to any task. The engine will attempt execution `1 + max_retries` times before marking the task failed.

```yaml
name: Retry on failure
capability: http
input:
  method: GET
  url: https://flaky.internal/api
max_retries: 3
```

`cond task list` will show `4 / 4` in the Attempts column if all retries were exhausted.

---

### Custom capability config

Load plugins or override the default capability config:

```bash
cond --config my-capabilities.yaml run task.yaml
```

Plugin config format:

```yaml
include_builtins: true
capabilities:
  - import_path: my_package.capabilities:CustomCapability
    config:
      api_base_url: https://example.internal
```
