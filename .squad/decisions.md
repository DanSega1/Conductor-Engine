# Squad Decisions

## [2026-04-30] Roadmap Session — Release Notes, Version Policy, Docs Workflow

---

### [2026-04-30] GitHub Release Notes Configuration — Kobayashi

Configure `python-semantic-release` v10.5.3 to automatically populate GitHub release bodies with full changelog content from conventional commits.

**Changes Made:**
- Updated `pyproject.toml`: Added `upload_to_release = true` and `[tool.semantic_release.changelog]` section with template config
- Created `.semantic_release_templates/release.md.j2`: Jinja2 template with "## What's Changed" header and full changelog
- Updated roadmap status to `done (2026-04-14)`

**Validation:** pyproject.toml valid TOML, template file created, release workflow permissions unchanged, Trusted Publishing preserved.

**Status:** Ready for next release.

---

### [2026-04-30] python-semantic-release Template Variable Standard — Fenster (QA)

Established standard for all PSR v10 templates in this project to use correct context variables.

**Issue Found:** Kobayashi's initial template used `{{ repo }}` which is not a standard PSR v10 variable.

**Standard Established:**
- Use `{{ owner }}` for repository owner (e.g., "DanSega1")
- Use `{{ repo_name }}` for repository name (e.g., "Conductor-Engine")
- Use `{{ version }}` for release version
- Use `{{ changelog }}` for formatted changelog
- Never assume `{{ repo }}` variable exists

**Impact:** Without fix, release links would be broken (`https://github.com/releases/tag/...`). With fix, links render as `https://github.com/DanSega1/Conductor-Engine/releases/tag/vX.Y.Z`.

**Status:** APPROVED. All agents should follow this pattern for future PSR templates.

---

### [2026-04-30] Semantic Release Version Policy — Keaton

**Decision:** Accept rapid bumping — `0.x` is explicitly unstable; version number does not imply maturity.

**Rationale:** Options 1-3 (squash-merge, `[skip release]`, scope filtering) add process friction without meaningful benefit for single-developer project in pre-1.0 phase. SemVer already defines 0.x as unstable — users expect rapid API changes. The real stability milestone is 1.0.0.

**Impact:** No change to current commit or release behavior. Continue using `feat:` commits; let semantic-release bump minor versions automatically. Document in README that `0.x` versions carry no stability guarantees. When approaching 1.0.0, revisit cadence controls if needed.

**Status:** Done. No code changes required.

---

### [2026-04-30] Docs Check Workflow Design — Kobayashi

Implemented `.github/workflows/docs-check.yml` to automate validation of documentation freshness per roadmap backlog item "Auto-update docs and README GitHub Action."

**Key Choices:**
1. **Workflow Isolation:** Separate workflow file with `continue-on-error: true` (non-blocking on merges)
2. **Mermaid Validation:** `@mermaid-js/mermaid-cli` (npx mmdc) — official CLI tool, npm-installable, lightweight
3. **Badge URL Checking:** curl-based HTTP status verification (200/302 = pass, 5s timeout) — no external action dependency
4. **Issue Creation:** `gh issue create` with ambient `GITHUB_TOKEN` (preserves Trusted Publishing)
5. **Trigger Paths:** `engine/**`, `docs/**`, `examples/**`

**Trade-offs:**
- Bash-heavy implementation: Easier to audit than custom action
- Strict URL validation skipped: Only checks badges; full link-checking deferred
- No PNG regeneration: Future enhancement (marked as deferred in roadmap)

**Status:** Implemented. Workflow ready for CI/CD pipeline.

---

## Active Decisions

---

### [2026-03-31] Use `rich` for CLI output — Hockney

Add `rich>=13` as a runtime dependency. Use `Panel` for `cond run`, borderless `Table` for `cond capability list` and `cond task list`. Status styled green/red. Attempts shown as `n / max` when retries configured. Dict/list output compacted to single-line JSON, truncated at 120 chars. `_json_dump` preserved. Errors to stderr via separate `Console(stderr=True)`. Alternatives rejected: `click` (no rendering), `typer` (full rewrite), `tabulate` (no panels/color).

---

### [2026-03-31] Retry Logic Design for TaskSupervisor — McManus

`max_retries` on `TaskSubmission` (per-call, not per-capability global). `attempt: int` and `max_retries: int` on `TaskRecord` for full observability. Loop: `while task.attempt <= task.max_retries`, increment at top, break on success. Default `max_retries=0` = one attempt (backward compat). Rejected: exponential backoff (out of scope), re-queuing (ordering complexity).

---

### [2026-03-31] Phase 2 Agent Layer Shape — Keaton

Orchestrator calls agents; agents do not call the supervisor. Supervisor unchanged. Role-specific context/response types replace generic `AgentContext`/`AgentResponse`: `PlannerContext`/`PlanResponse`, `WorkerContext`/`WorkerResponse`, `ValidatorContext`/`ValidationResponse`. Base `AgentInterface` Protocol stays broad; orchestrator holds typed `PlannerInterface`, `WorkerInterface`, `ValidatorInterface` subtypes. `engine/workflow/` is the Phase 2 home. Deferred: LLM backends, parallel steps.

---

### [2026-04-01] Workflow Contracts — McManus

`WorkflowGoal.capabilities` is the single hand-off from caller to orchestrator. `PlanStep.input_hint` is advisory (not binding — worker resolves concrete submission). `WorkflowResult.verdict` is `ValidationResponse | None` to support validator-less workflows. `WorkflowResult` persistence deferred to Phase 3. `ValidationResponse` lives in `workflow.py` (co-located with `ValidatorContext`/`ValidatorInterface`). `agent.py` untouched — workflow role interfaces are parallel, not derived from `AgentInterface`.

---

### [2026-04-01] WorkflowOrchestrator Test Strategy — Fenster

Hand-written stub classes (`StubPlanner`, `CapturingWorker`, `CapturingValidator`, `FailingTaskSupervisor`) over `pytest-mock`. `FailingTaskSupervisor` returns pre-built FAILED record to isolate orchestrator control-flow from guardrail behavior. `MemoryTaskStore` in `_make_supervisor` to avoid filesystem I/O. `prior_results` accumulation verified through `CapturingWorker` context objects. Edge cases flagged: zero-step plan, optional validator (None), exception from supervisor (not FAILED record).

---

### [2026-04-01] Platform Vision — Autonomous Operation, Guild Layer, Remote Deployment — Dan

Target operational model: mostly-autonomous crew running without a human watching. Key principles: (1) human-in-the-loop optional; (2) self-reinforcing rules via guardrails, OPA, retry/recovery at platform level; (3) behavioral retry — accumulate knowledge from failure; (4) guild-layer cross-project knowledge sharing (Phase 6); (5) remote-first deployment (VPS/cloud); (6) OPA + guardrails as platform-level, not add-on.

---

### [2026-04-01] Archive-over-delete — Dan

Task records, workflow records, and any engine state must NEVER be hard-deleted. All cleanup operations must archive: move to a cold store, mark with `archived_at`, or write to an archive collection. Delete is not a valid operation in the engine. Applies to all phases and all store backends.

---

### [2026-04-01] Addon Boundary — Keaton

`conductor-engine` (the PyPI package) must function with `pip install conductor-engine`, a filesystem or in-memory store, and zero external services forever. Addons are anything that requires an external service, is domain-specific, or is optional for function. Core: `echo`/`filesystem`/`http`/`memory` capabilities, `LinearOrchestrator`, passthrough agents, `MemoryTaskStore`/`LocalTaskStore`, null/logging event bus; optional extras: SQLite, Postgres, Redis stores; separate addons: LLM planners (`conductor-openai`, `conductor-anthropic`), OPA (`conductor-opa`), guild store (`conductor-guild`), auth plugins (`conductor-auth-*`). Remote API server is engine-core (Phase 7). TUI is a separate Go binary. All addon packages follow `conductor-{name}`.

---

### [2026-04-01] Cross-Phase State Tracking & Design Integrity — Keaton

Two mechanisms adopted to keep design integrity visible across phases: (1) `health_check() -> list[str]` per component — verifies structural invariants at runtime (not a substitute for tests; empty list = healthy); callable via `cond health` in Phase 4 and at startup. (2) `docs/conductor/design-integrity.md` living doc — lists every cross-phase invariant with status (guaranteed / at-risk / broken), the phase that introduced it, components spanned, and any known threats.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
