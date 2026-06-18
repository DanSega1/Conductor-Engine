# cond CLI

`cond` is the command-line interface for Conductor Engine. It lets you run tasks, inspect capabilities, and review task history from a terminal.

## Installation

```bash
pip install -e .
```

## Commands

### `cond serve`

Start the HTTP control-plane API server (FastAPI / Uvicorn).

```bash
cond serve
cond serve --host 0.0.0.0 --port 8080
```

Requires the `[api]` extra: `pip install -e ".[api]"`.

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8080` | TCP port |
| `--policy` | `risk` | Policy engine: `risk` (deny above HIGH), `deny-all` (block everything), `null` (allow all) |
| `--tls-cert` | — | Path to TLS certificate file (enables HTTPS) |
| `--tls-key` | — | Path to TLS private key file |
| `--api-key-path` | `.conductor/api_keys.json` | Path to API key store (auto-enabled when TLS is active) |

When the API key store is empty, the API runs in open mode for backward compatibility.

---


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

### `cond api-key generate`

Generate a new API key for HTTP API authentication.

```bash
cond api-key generate
cond api-key generate --actor deploy-bot --scope "*"
cond api-key generate --actor ci-runner --scope "task:submit" --scope "task:list"
```

The raw key is printed exactly once. Keys are stored as SHA-256 hashes.

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--actor` | `"anonymous"` | Human-readable actor name |
| `--scope` | `["*"]` | Authorization scopes (repeatable) |
| `--store` | `.conductor/api_keys.json` | Path to API key store file |

---

### `cond api-key list`

List all API keys with prefix, actor, scopes, and revocation status.

```bash
cond api-key list
```

**Output:**
```
 Prefix           Actor        Scopes     Revoked
 cond_a1b2c3…     default      *          no
 cond_d4e5f6…     deploy-bot   task:*     yes
```

---

### `cond api-key revoke <prefix>`

Revoke an API key by its prefix. Running servers detect the change on next request via file mtime check.

```bash
cond api-key revoke cond_a1b2c3
```

---

### `cond guild list`

List all failure knowledge records stored in the guild knowledge base.

```bash
cond guild list
```

---

### `cond guild show <key>`

Show a single guild record with full failure context and resolution hints.

```bash
cond guild show echo:TimeoutError:abc123
```

---

### `cond guild clear`

Remove all guild records from the store.

```bash
cond guild clear
```

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
