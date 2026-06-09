# Conductor Engine — Roadmap

A minimal, composable orchestration runtime. The goal at every phase is to stay small enough that other programs can build on top of it cleanly.

## Vision

Conductor Engine is a substrate for autonomous systems. The target operational model is a crew that runs mostly unattended — humans provide tasks, direction, and course corrections, but the platform enforces its own rules, recovers from failure, and learns over time without requiring a human in the loop at every step.

Key principles:
- **Human-in-the-loop is optional** — the platform is safe to run unattended
- **Rules are self-enforcing** — guardrails and policies are platform-level, not caller-level
- **Remote-first** — runs on a local machine, VPS, or cloud instance with no architectural difference
- **Learning from failure** — the platform accumulates knowledge and applies it, not just retries
- **Guild knowledge** — workers share learning curves and solutions across projects

---

## Phase 1 — Core Runtime (complete)

Single-process task execution with a pluggable capability surface.

- Task model: `TaskSubmission` → `TaskRecord`, state machine `PENDING → RUNNING → COMPLETED / FAILED`
- Supervisor: validates input, resolves capability, executes, persists result
- Capability registry: built-ins (echo, filesystem, http, memory) + YAML plugin loading
- Guardrails: input validation before a task leaves PENDING
- Retry logic: `max_retries` on task submission, attempt counter on record
- Local store: JSON task store + in-memory queue
- CLI: `cond run`, `cond capability list`, `cond task list` with rich terminal output
- CI/CD: ruff + pytest on push, semantic release → PyPI

---

## Phase 2 — Workflow Layer (complete)

Multi-step task execution via agent roles. The supervisor stays untouched; a thin orchestrator sits above it.

### Step 1 — Workflow contracts

**File:** `engine/interfaces/workflow.py`

Add role-specific Pydantic types:
- `WorkflowGoal`, `PlanStep`, `WorkflowResult`
- `PlannerContext` / `PlanResponse`
- `WorkerContext` / `WorkerResponse`
- `ValidatorContext` / `ValidationResponse`

This is the public interface external consumers implement against. Must be stable before the orchestrator is built.

### Step 2 — WorkflowOrchestrator

**File:** `engine/workflow/orchestrator.py`

Synchronous coordinator:

```
WorkflowGoal
  → Planner        → PlanResponse(steps)
  → for step:
      Worker       → WorkerResponse(TaskSubmission)
      Supervisor   → TaskRecord            ← unchanged Phase 1 path
  → Validator      → ValidationResponse
  → WorkflowResult
```

No new infrastructure — orchestrates existing machinery. Fail-fast on the first failed step.

### Step 3 — Stub agents

**Dir:** `engine/workflow/agents/`

- `LinearPlanner` — ordered steps from a structured goal, no LLM required
- `PassthroughValidator` — always passes; opt-in to real validation

Required for integration tests and `examples/` without external dependencies. These are also the extension points downstream consumers override.

### Step 4 — Workflow CLI + examples

**Command:** `cond workflow run <file.yaml>`

Accepts a workflow YAML (goal + step list). One `examples/` workflow chaining two capability calls end to end.

---

## Phase 3 — Production Hardening (complete)

Stability, observability, and deployment-readiness.

### Done
- Extended `TaskStatus`: `AWAITING_APPROVAL`, `APPROVED`, `POLICY_DENIED`, `CANCELLED`
- `AuditEntry` model + `audit_trail` on `TaskRecord`
- `workflow_id` and `archived_at` on `TaskRecord` (archive-over-delete)
- `ValidatorInterface` → ABC (enforcement, not duck-typing)
- `TaskStore.list()` pagination: `limit`, `offset`, `status` filter
- **EventBus**: `TaskEvent`, `EventBus` Protocol, `NullEventBus` (default), `LoggingEventBus`; supervisor emits `task_started` / `task_completed` / `task_failed`
- PolicyEngine interface — authorize-before-execute hook in supervisor; null policy by default
- Safe sync/async bridge in `async_utils.py` — async providers can execute inside active event loops without adding async public APIs yet
- `cond health` command — `health_check() -> list[str]` per component
- `design-integrity.md` — living doc for cross-phase invariants ✓ (updated 2026-04-14)
- `MCPCapability` seam — capability wrapper for addon-provided MCP executors; concrete transport stays in `conductor-mcp`
- Pluggable task store backends (Postgres, SQLite, Redis)
- Parallel step execution in the orchestrator via adjacent `parallel_group` batches, with failure isolation at the batch boundary
- Runtime-configured execution controls per capability: soft timeouts and min-interval rate limiting
- Approval flows: tasks can pause in `AWAITING_APPROVAL`, resume via `APPROVED`, or terminate via `CANCELLED`

---

## Phase 4 — Control Plane + TUI (complete)

A versioned HTTP control-plane API that `condor-tui`, wrapper services, and future web UIs consume without coupling to internal Python objects.

### Done

- **`engine/api/`** — full FastAPI control-plane API, optional `[api]` install extra
- **Versioned read models** — `ControlPlaneTaskV1`, `ControlPlaneWorkflowTraceV1`, `ControlPlaneCapabilityV1`, `ControlPlaneSnapshotV1`, `ControlPlaneEventV1` (all in `engine/control_plane/contracts.py`)
- **Task routes** — `GET/POST /v1/tasks`, `/v1/tasks/run`, `/{id}/run`, `/{id}/approve`, `/{id}/cancel`
- **Capability routes** — `GET /v1/capabilities`, `GET /v1/capabilities/{name}`
- **Workflow routes** — `POST /v1/workflows`, `GET /v1/workflows/{workflow_id}`
- **Observability routes** — `GET /v1/health` (503 on issues), `GET /v1/snapshot`
- **SSE event stream** — `GET /v1/events` with type-filter query param; `SSEEventBus` bridges sync supervisor threads to async SSE clients via `loop.call_soon_threadsafe`
- **Multi-engine cluster** — `GET/POST /v1/engines`, heartbeat, deregister, tag-based auto-routing at `POST /v1/engines/tasks/run`; proxy health and snapshot to remote nodes via httpx
- **Auth placeholder** — `AuthContext` + `get_auth_context` dependency in `engine/api/dependencies.py`; Phase 7 replaces the implementation without touching route handlers
- **`cond serve`** — CLI subcommand wires the full engine stack and launches uvicorn
- **OpenAPI docs** — auto-generated at `/docs` and `/redoc` from existing Pydantic v2 models
- **`Dockerfile` + `.dockerignore`** — `python:3.14-slim`, verified on `linux/arm64`; `cond serve` as entrypoint
- **31-test API suite** — `tests/engine/test_api.py` covering all route groups via `TestClient`

**`condor-tui`** (`DanSega1/condor-tui`) consumes the API over HTTP — polls `/v1/snapshot`, subscribes to `/v1/events`, and drives control actions through the task endpoints.

---

## Phase 5 — Autonomous Operation (complete)

The platform enforces its own rules and recovers without a human present.

### Done

- **Slice 1 — Failure contracts and escalation wiring** — `FailureContext`, `RetryStrategy`, `DefaultRetryStrategy` (with `enable_escalation`), `TaskStatus.ESCALATED`, `EventType.TASK_ESCALATED`, and full supervisor wiring.
- **Slice 2 — Escalation threshold and CLI visibility** — `escalation_threshold` on `DefaultRetryStrategy`. ESCALATED tasks appear in `cond task list` with ⚠ bold-yellow marker.
- **Slice 3 — OPA policy integration** — `OPAPolicyEngine`, `RiskLevelPolicyEngine`. Both plug into the existing `PolicyEngine` Protocol without touching the supervisor.
- **Slice 4 — Cron/webhook trigger adapters** — `CronTriggerAdapter`, `WebhookTriggerAdapter` with deterministic poll semantics.
- **Slice 5 — Trigger scheduler service** — `TriggerSchedulerService` polls adapters and submits dispatches through the supervisor path.
- **Slice 6 — Webhook ingress boundary** — `WebhookIngressService` routes decoded webhook payloads to named adapters.
- **Slice 7 — Scheduler lifecycle controls** — `TriggerSchedulerLoopRunner` with exponential idle backoff, jitter, max-cycle bounds, and graceful stop-signal shutdown.
- **Slice 8 — Behavioral retry strategies** — `ExponentialBackoffRetryStrategy`, `JitteredBackoffRetryStrategy`, `InputAdjustingRetryStrategy`. All implement `RetryStrategy` Protocol; supervisor already handles `delay_seconds` and `adjusted_input`.
- **Slice 9 — Production HTTP bindings for webhook ingress** — `POST /v1/triggers/{name}`, `GET /v1/triggers`; `trigger_service` param on `create_api_app`.
- **Slice 10 — Human-in-the-loop as a configured mode** — `require_approval: bool` on `CapabilityDescriptor`; supervisor gates every task using that capability at `AWAITING_APPROVAL` before the policy engine is consulted. Declarable in YAML capability config via `require_approval: true`.
- **Slice 11 — Sandboxed subprocess execution** — `SubprocessCapabilityRunner` and `_sandbox_worker` module execute capabilities in isolated child processes with hard wall-clock timeout, no shared state, and clean resource reclamation. Opt-in; existing in-process path unchanged.
- **Slice 12 — Richer audit trail for policy decisions** — every `_apply_policy` call now stamps `policy_engine` (class name) and `decision_type` into the audit entry metadata, regardless of allow/deny/require_approval outcome.
- **Slice 13 — Integration test suite** — `tests/integration/test_control_plane_integration.py`; 17 tests across: control-plane schema stability, require_approval gate, webhook→scheduler→store end-to-end, policy deny audit trail, retry with backoff, sandboxed subprocess execution.

---

## Phase 6 — Guild Layer

Workers and roles share learning across projects.

The "guild" is a cross-project knowledge layer — a structured way for agent roles to publish what they learned from a hard task, a failure pattern, or an edge case, and for other instances of the same role to discover and apply that knowledge.

- **Failure knowledge base** — when a task fails after max retries, the failure context is published to the guild store (capability, input shape, error class, resolution if found).
- **Peer suggestions** — before attempting a task similar to a known failure, the runtime checks the guild for prior resolutions and applies them as input hints or approach adjustments.
- **Role-scoped knowledge** — a worker role in Project A can learn from a worker role in Project B that hit the same capability failure.
- **No centralized model required** — guild knowledge is structured data (capability + error fingerprint → resolution hint), not LLM embeddings. Works without a model in the loop.
- **Opt-in per deployment** — guild participation is configured, not automatic. A deployment that handles sensitive data can operate fully isolated.

---

## Phase 7 — Remote Deployment and Protected Operation

Conductor running on a VPS, cloud instance, or remote machine — protected, efficient, and auditable.

- **Protected control plane** — harden the Phase 4 API with authn/authz, secret handling, transport security, and operational defaults fit for remote use.
- **Authentication and authorization** — API calls require auth. OPA policies govern what callers can submit (which capabilities, which inputs, under what conditions).
- **Multi-tenant isolation** — separate capability registries, task stores, and guardrail policies per tenant.
- **Efficient resource management** — capability concurrency limits, queue depth controls, backpressure when the system is under load.
- **Remote runners and CI targets** — remote machines, CI pipelines, and protected workers register as execution targets without bypassing supervisor, policy, or audit boundaries.
- **Deployment targets** — single binary (via a thin Go wrapper or containerized Python), `systemd` unit, Docker image, Kubernetes operator pattern.
- **Protected by default** — no capability executes without a policy allow decision. Default-deny with explicit permit grants.

This is the "OpenClaw-style but more protected and efficient" target — a hardened, remotely-operated orchestration platform with policy enforcement and a learning layer.

---

## Platform layering (decided)

The engine should stay versatile by keeping reusable platform concerns low in the stack and product-specific concerns above it.

- **Core engine** — supervisor lifecycle, workflow orchestration, policy, storage contracts, event model, control-plane API, and addon seams
- **Addon layer** — reusable extensions such as memory providers, MCP bridges, schedulers/cron triggers, SDK clients, and remote runner adapters
- **Product layer** — `condor-tui`, a future web UI, SDLC/CI wrappers, and domain-specific orchestration systems built on the core contracts

Rule of thumb:
- If the feature changes execution semantics or adds reusable infrastructure, put it in the engine or addon layer.
- If the feature is presentation, domain opinion, or product workflow, keep it in a wrapper project above the engine.

## Out of scope (explicitly)

These belong in programs built *on top of* Conductor, not inside it:

| Item | Why |
|---|---|
| LLM-backed planner | Domain concern — implement `PlannerContext`/`PlanResponse` externally |
| Distributed task queues (Redis, Celery) | Infrastructure — compose it in, don't embed it |
| Persistent workflow state across restarts | Downstream storage concern until Phase 3 defines the store interface |
| Copilot / agent framework | Conductor is the substrate; agents are consumers |
| Product-specific UI beyond the reference clients | A web dashboard or vertical wrapper can be built on top of the control plane, but it is not a platform primitive |

---

## Backlog — Engineering & Developer Experience

Cross-cutting tasks not tied to a specific phase. Prioritised roughly — address before / during Phase 3.

### Integration tests that mimic user/wrapper/TUI activity

Status: planned (Phase 5 follow-up)

Add an integration suite that validates end-to-end operator and wrapper flows against control-plane contracts:
- Simulate user-like activity through CLI and wrapper-style task submissions, then assert task status progression, audit visibility, and approval transitions.
- Simulate TUI-style read patterns (list/watch/trace) against versioned contracts to verify schema stability as Phase 4 and Phase 5 evolve.
- Cover webhook-triggered submissions through scheduler ingress to supervisor submit path and assert trigger metadata provenance in stored task records.
- Add regression fixtures to ensure external consumers (CLI wrappers and TUI clients) do not break when runtime internals change.

### ⚠️ Time-sensitive: GitHub Actions — Node.js 24 migration (deadline: June 2, 2026)

Status: done (2026-04-02) — Upgraded workflow action pins to Node.js 24–compatible versions in `ci.yml` and `release.yml`.

Node.js 20 actions are deprecated. GitHub will force Node.js 24 by default on **June 2, 2026**; Node.js 20 is removed entirely on **September 16, 2026**.

Actions to upgrade in `.github/workflows/`:

| Workflow | Action | Current | Required |
|---|---|---|---|
| `ci.yml`, `release.yml` | `actions/checkout` | `v4` | confirm Node.js 24 compatible (check latest tag) |
| `release.yml` | `actions/setup-python` | `v5` | confirm Node.js 24 compatible |
| `release.yml` | `actions/upload-artifact` | `v4` | confirm Node.js 24 compatible |
| `release.yml` | `actions/download-artifact` | `v4` | confirm Node.js 24 compatible |

Resolution: check each action's releases for a Node.js 24–compatible tag and pin to it. Optionally opt in early by setting `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` in the workflow env.

---

### Release notes on GitHub releases

Status: done (2026-04-14) — Configured `semantic_release` to populate GitHub release bodies with full changelog from conventional commits. Added `upload_to_release = true`, created `.semantic_release_templates/release.md.j2` with "What's Changed" section, and linked template in `pyproject.toml`.

---

### Rename `try-it/` → `examples/` with better explanations

Status: done (2026-04-02) — Renamed the example directory, documented each runnable example, and added an `examples/README.md` index.

The `try-it/` directory name is not idiomatic. Replace it with `examples/`:
- Rename `try-it/` to `examples/`
- Each example file gets a docstring or leading comment block explaining: what it demonstrates, what capabilities it uses, how to run it (`cond workflow run examples/<file>.yaml`)
- Add an `examples/README.md` index listing all examples with one-line descriptions
- Update all references in `README.md`, `docs/`, and `CHANGELOG.md`

---

### README overhaul

Status: done (2026-04-02) — Reworked the README with badges, banner artwork, architecture overview, AI disclosure, a Python 3.14 quick start, and stronger docs/examples links.

The README needs a first-class presence for a published library. Items:
- **Badges row** — CI status, PyPI version, Python versions, license, coverage (once wired)
  ```markdown
  [![CI](https://img.shields.io/github/actions/workflow/status/DanSega1/Conductor-Engine/ci.yml?branch=main&logo=github&label=CI)](...)
  [![PyPI](https://img.shields.io/pypi/v/conductor-engine.svg)](https://pypi.org/project/conductor-engine/)
  [![Python](https://img.shields.io/pypi/pyversions/conductor-engine.svg)](...)
  [![License](https://img.shields.io/github/license/DanSega1/Conductor-Engine.svg)](LICENSE)
  ```
- **Banner image** — a header graphic or architecture overview image at the top
- **Architecture diagram** — embed the Mermaid execution-flow diagram from `docs/conductor/architecture-diagrams.md` (or a rendered PNG) in the README
- **AI disclaimer** — section near the top: *"This project is AI-enhanced. A significant portion of the code, tests, and documentation was written with AI assistance as part of an intentional human-AI collaborative workflow."*
- **Quick-start** — tighten the install + first-run example to under 10 lines
- **Links** to `examples/`, `docs/conductor/roadmap.md`, and the PyPI page

---

### Auto-update docs and README GitHub Action

**Status: done (2026-04-30)** — Created `.github/workflows/docs-check.yml` with Mermaid validation and badge URL link-check jobs.

Create a workflow that keeps generated content fresh without manual effort:
- Trigger: push to `main` that touches `engine/**`, `docs/**`, or `examples/**`
- Jobs:
  - Validate all Mermaid diagrams render without error
  - Check that README badge URLs resolve (link checker)
  - (Future) Re-render architecture PNG from Mermaid source and commit if changed
- Keep this separate from CI so failures here don't block merges, they create issues

---

### Isolated capability execution for hard timeouts and cancellation

Phase 3 added runtime-configured `execution_controls`, but `timeout_seconds` is intentionally a soft in-process wrapper. The supervisor can mark a task failed after the deadline, but it cannot forcibly terminate arbitrary user code or guarantee prompt cancellation while capabilities run in the same process.

Future work:
- Add an optional isolated capability executor boundary (subprocess first, stronger sandboxing later)
- Route hard timeout enforcement and stronger cancellation semantics through that isolated executor path, not the current thread-based wrapper
- Keep supervisor-owned state transitions, audit entries, and event emission authoritative even when an isolated executor is killed
- Preserve the current in-process executor as the minimal default for local built-ins and simple deployments

---

### CLI docs sync rule

When a stable CLI command, flag, or help surface changes, update all relevant docs in the same change:
- `README.md` for user-facing quick-start or top-level usage changes
- `docs/conductor/cond-cli.md` for detailed CLI reference updates
- `docs/man/cond.1` for stable native manual coverage

Rule of thumb:
- If the change affects `cond --help`, command names, flags, or stable command behavior, update the manpage too
- If the change only affects runtime capability help or registry-derived output, update `cond help` behavior/docs and skip the manpage unless the stable CLI contract changed

---

### Post-phase self-checkup rule

After completing each phase (marked as `complete` in the roadmap), run a structured review before starting the next:

1. **Full test suite** — `pytest tests/ -q`; zero failures required to proceed
2. **Lint clean** — `ruff check engine/ tests/ cli/`; zero errors
3. **Flaw search** — review architecture decisions for gaps introduced by the phase; update `docs/conductor/design-integrity.md`
4. **Integration smoke** — run at least one end-to-end example from `examples/` against a real store (not mocks)
5. **Edge case audit** — review new interfaces for: missing defaults, None-safety, serialization round-trips, backward compatibility
6. **Roadmap update** — mark phase `(complete)`, update `### Done` / `### Remaining` lists

This checklist is enforced by convention, not automation, until Phase 3 delivers `cond health`.

---

### Python 3.14 upgrade + single venv

Status: done (2026-04-02) — Bumped the package and GitHub Actions to Python 3.14 and documented the single `.venv` bootstrap convention.

- Bump `requires-python` in `pyproject.toml` from `>=3.12` to `>=3.14`
- Update `actions/setup-python` target in `ci.yml` and `release.yml` to `python-version: "3.14"`
- Add `3.14` to the Python version badge in the README
- **Single venv rule**: the repo should have exactly one `.venv` directory. Convention going forward: `.venv/` at repo root, created with `python3.14 -m venv .venv`. Add `.venv*/` to `.gitignore` (already covered by `.venv*`) and document the bootstrap command in `README.md`.

---

### Semantic release version policy — review and tighten

Status: done (2026-04-30) — Decided: Accept rapid bumping; 0.x versions carry no stability guarantee, real milestone is 1.0.0. See decisions.md.

---

### CI path scoping — don't trigger on non-code changes

Status: done (2026-04-02) — Restricted CI triggers to code, test, packaging, and workflow files so docs-only changes no longer run the suite.

`ci.yml` currently fires on every push and every PR regardless of what changed. A typo fix in `docs/` or a `.squad/` memory update runs the full lint+test suite unnecessarily.

Add `paths` filters to `ci.yml`:

```yaml
on:
  pull_request:
    paths:
      - "engine/**"
      - "cli/**"
      - "tests/**"
      - "pyproject.toml"
      - "requirements-test.txt"
      - "ruff.toml"
      - ".github/workflows/ci.yml"
      - ".github/workflows/release.yml"
  push:
    branches: [main]
    paths:
      - "engine/**"
      - "cli/**"
      - "tests/**"
      - "pyproject.toml"
      - "requirements-test.txt"
      - "ruff.toml"
      - ".github/workflows/ci.yml"
      - ".github/workflows/release.yml"
```

Paths that should **not** trigger CI: `docs/**`, `.squad/**`, `*.md`, `.github/workflows/squad-*.yml`, `examples/**`.

Do the same for `release.yml` — docs-only pushes to `main` should not attempt a release calculation.

---

### Release gate — require CI to pass before build

Status: done (2026-04-02) — Switched `release.yml` to `workflow_run` and gated publishing on successful `CI` runs from `main`.

`release.yml` currently runs independently of `ci.yml`. A push to `main` can trigger a PyPI publish before tests have passed (CI and release are separate workflow runs that race).

Fix: add a `workflow_run` trigger to `release.yml` so it only proceeds after `CI` completes successfully:

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
```

And gate the `release` job on the triggering workflow's conclusion:

```yaml
jobs:
  release:
    if: github.event.workflow_run.conclusion == 'success'
```

This enforces: **conventional commits → lint → tests → version calc → build → publish**. No step can bypass the chain.

Also consider adding the build as an explicit step before the `python-semantic-release` action rather than relying on its internal `build_command` — makes the build output inspectable in the Actions log.

---

### Build contents — include only library essentials

Status: done (2026-04-02) — Added package excludes plus `MANIFEST.in`, then verified the built wheel only contains `cli/`, `engine/`, and dist-info.

Verify the published wheel and sdist contain only what consumers need. Current `pyproject.toml` includes `cli*` and `engine*` via `setuptools.packages.find`. Check and tighten:

- **Include:** `engine/`, `cli/` (the `cond` entry point)
- **Exclude from sdist:** `tests/`, `docs/`, `.squad/`, `examples/`, `.github/`
- Add an explicit `[tool.setuptools.packages.find] exclude` list
- Add a `MANIFEST.in` (or `tool.setuptools` config) to prune non-essential files from the sdist
- After a local build (`python -m build`), inspect with `tar tzf dist/*.tar.gz | sort` to verify nothing extraneous bleeds in

---

### Hybrid `man cond` + `cond help`

Status: done (2026-04-02) — Added a packaged native `cond.1` manpage for stable CLI docs while keeping `cond help` for runtime-aware command and capability help.

Add a hybrid offline help system:

```
man cond                      # stable CLI manual
cond help                     # list runtime-aware topics
cond help echo                # capability spec: inputs, outputs, risk level, examples
cond help filesystem          # same for filesystem capability
cond help workflow            # workflow YAML format reference
cond help run                 # detail on cond run flags and behaviour
```

Implementation:
- Each `Capability` class can optionally expose a `man_page() -> str` method; falls back to `descriptor.description` + input schema introspection if not implemented
- `cond help` output is rendered with `rich` (headings, parameter table, example block) — same style as existing CLI panels
- `cond help` with no argument prints a topic index derived from the registry and a hardcoded set of built-in command topics
- `man cond` covers the stable core CLI surface only; dynamic capability and plugin-aware help remains under `cond help`
- No external dependency; pure Python + rich
