# Conductor Engine

A minimal, installable orchestration runtime for task execution, capability loading, guardrails, storage abstractions, and future agent/policy layers.

## What It Includes

- Generic task contracts and supervisor runtime
- Capability registry and plugin loading
- Built-in `echo`, `filesystem`, `http`, and optional `memory` capabilities
- Optional memU-backed memory provider abstraction
- Local JSON task store and in-memory queue
- `cond` CLI for local task execution and inspection
- Docs-first engine contracts under `docs/conductor/`

## Quick Start

```bash
pip install -e .
cond capability list
cond run task.yaml
cond task list
```

Example task:

```yaml
name: Echo smoke test
capability: echo
input:
  message: hello from conductor
```

## Repository Layout

```text
Conductor-Engine/
  engine/
  cli/
  docs/
  config/
  tests/
```
