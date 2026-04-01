# Kobayashi — History

## Core Context

**Project:** Conductor-Engine — Python 3.12+ orchestration runtime (Pydantic v2, httpx, pyyaml)
**Owner:** Dan
**Role:** DevOps & Release

## Learnings

### 2026-03-31 — Project kickoff
- CI runs on push/PR: conventional commit validation → `ruff check .` → `pytest tests/engine -q`
- Release automation: Python Semantic Release calculates version from Conventional Commit history, creates tag, builds package, publishes to PyPI
- PyPI uses Trusted Publishing — `release.yml` is the trusted workflow; no stored secrets needed
- Current version: 0.1.1 (in `pyproject.toml`)
- `chore(release): {version} [skip ci]` commits are auto-generated — do not manually bump the version field
- `CHANGELOG.md` is auto-maintained by semantic-release — do not hand-edit it
- Ruff config is in `ruff.toml` — check it before adding/removing lint rules
