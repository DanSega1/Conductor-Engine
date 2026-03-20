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

## Automation

- `.github/workflows/ci.yml` validates Conventional Commit messages, runs `ruff check .`, and runs `pytest tests/engine -q`.
- `.github/workflows/release.yml` uses Python Semantic Release to calculate the next version, tag the release, build the package, and publish it to PyPI.
- PyPI publishing is configured for Trusted Publishing through the `pypi` GitHub environment. On PyPI, register this repository and the `.github/workflows/release.yml` workflow as the trusted publisher.
- If you want the current `0.1.0` in `pyproject.toml` to be the baseline release, create and push `v0.1.0` before enabling the release workflow. Otherwise, semantic-release will calculate the next version from commit history.
