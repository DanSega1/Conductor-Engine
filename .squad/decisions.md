# Squad Decisions

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
