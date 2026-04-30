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

### 2026-04-14 — GitHub Release Notes Configuration
- semantic-release v10.5.3 supports `upload_to_release = true` to auto-populate GitHub release bodies
- Custom release body templates go in `.semantic_release_templates/` and are referenced via `[tool.semantic_release.changelog.default_templates]` in `pyproject.toml`
- Template files use Jinja2 format (`.j2` extension) with context vars like `{{ changelog }}`, `{{ version }}`, `{{ repo }}`
- Release workflow already has `contents: write` permission (required for semantic-release to create/update releases)
- **Template pattern**: `.semantic_release_templates/release.md.j2` with `## What's Changed` section + full changelog
- Config key: `release_body = "release.md.j2"` (no path prefix — semantic-release looks in template_dir)

### 2026-04-30 — Docs Check Workflow Implementation
- Created `.github/workflows/docs-check.yml` for automated docs validation
- **Trigger**: Push to `main` affecting `engine/**`, `docs/**`, or `examples/**` paths
- **Two jobs**: (1) Mermaid diagram validation via `@mermaid-js/mermaid-cli`, (2) README badge URL checking via curl
- **Design principle**: Keep workflow separate from CI — use `continue-on-error: true` on both jobs so failures create issues, not block merges
- **Issue creation**: When failures occur, workflow uses `gh issue create` with `GITHUB_TOKEN` (no PAT needed) to report problems with workflow run link
- **Permissions**: `contents: read` for checkout, `issues: write` for issue creation
- **No new dependencies**: Uses npm-installable `@mermaid-js/mermaid-cli` and built-in curl; no Python deps added
- **Mermaid validation strategy**: Extract mermaid blocks from markdown, pipe to mmdc stdin with `--dry-run`; badge check uses curl status codes (200, 302 = ok)
- Marked roadmap item "Auto-update docs and README GitHub Action" as done
