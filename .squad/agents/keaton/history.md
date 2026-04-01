# Keaton — History

## Core Context

**Project:** Conductor-Engine — Python 3.12+ orchestration runtime (Pydantic v2, httpx, pyyaml)
**Owner:** Dan
**Team:** Keaton (Lead), McManus (Backend), Hockney (CLI), Fenster (Tester), Kobayashi (DevOps)

## Learnings

### 2026-03-31 — Phase 2 agent layer design
- **Orchestrator pattern wins over enriching the supervisor.** New `WorkflowOrchestrator` sits above `TaskSupervisor`. Supervisor gets zero agent knowledge, Phase 1 callers untouched.
- **Agents do not call the supervisor.** Orchestrator calls agents, orchestrator calls supervisor. Clean unidirectional dependency.
- **Generic AgentContext/AgentResponse are wrong for Phase 2 dispatch.** Role-specific types (PlannerContext/PlanResponse, WorkerContext/WorkerResponse, ValidatorContext/ValidationResponse) replace them at call sites. Base Protocol stays generic for structural typing only.
- **PlanStep.input_hint is advisory.** Worker owns producing the final TaskSubmission; planner suggests inputs but is not required to know full capability input schemas.
- **Phase 2 is one linear pass.** No retry, no replanning, no parallel steps yet. Fail-fast on first FAILED step.
- **Workflow persistence is deferred.** TaskRecords are persisted per step; WorkflowResult is in-memory until a store design exists.
- **New package boundary:** `engine/workflow/` owns orchestration; `engine/supervisor/` owns single-task execution. These must not cross.

### 2026-04-01 — Cross-phase state tracking + addon boundary
- **HealthContract pattern adopted.** Each component exposes `health_check() -> list[str]` — empty = invariants hold. These are design contracts, not tests. CI can call them; `cond health` command (Phase 4) surfaces them.
- **`design-integrity.md` will be created at Phase 3 kickoff.** Living doc listing every cross-phase invariant with status: guaranteed / at-risk / broken. Keaton reviews before every phase merge.
- **Six pre-Phase-3 blockers identified:** (1) `workflow_id` + `archived_at` on `TaskRecord`; (2) `TaskStore.list()` pagination; (3) `ValidatorInterface` → ABC; (4) `TaskEvent`/`EventBus` interface; (5) replace `async_utils.py`; (6) `PassthroughWorker` input bridge.
- **Archive directive is absolute.** No `TaskRecord` or engine artifact is ever hard-deleted. `archived_at: datetime | None` field. No `delete()` on `TaskStore` — only `archive()`.
- **Addon boundary is fixed.** Engine core = zero external service deps at `pip install conductor-engine`. LLM planners, OPA, guild, MongoDB, TUI, and auth plugins are all addons (`conductor-{name}`). SQLite/Postgres/Redis ship as optional extras.
- **Target user locked:** individual → small team. Solo dev on a home lab should run forever with `LocalTaskStore` and built-in capabilities. Every external service dep must be genuinely optional with graceful no-op defaults.
- **Phase 7 remote API stays in core** — it's the platform surface. Auth/multi-tenant plugins are addons.

### 2026-03-31 — Project kickoff
- Phase 1 is complete: Supervisor, registry, capabilities (echo, filesystem, http, memory), local JSON store, in-memory queue, `cond` CLI
- Phase 2 is planned: agent roles (planner, worker, validator) per `docs/conductor/agent-interface.md`
- The engine is intentionally minimal — resist adding scope that isn't in docs
- Docs under `docs/conductor/` are the canonical contracts; code must follow them
- PyPI publishing uses Trusted Publishing via `release.yml` — do not add stored tokens
