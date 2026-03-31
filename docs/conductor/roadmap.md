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

## Phase 2 — Workflow Layer

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

Required for integration tests and `try-it/` examples without external dependencies. These are also the extension points downstream consumers override.

### Step 4 — Workflow CLI + examples

**Command:** `cond workflow run <file.yaml>`

Accepts a workflow YAML (goal + step list). One `try-it/` example chaining two capability calls end to end.

---

## Phase 3 — Production Hardening

Stability, observability, and deployment-readiness.

- Async supervisor and orchestrator (`async_utils.py` already in place)
- Structured logging with configurable output (JSON for aggregators, plain for terminals)
- Health and metrics endpoint (lightweight HTTP, no framework dependency)
- Pluggable task store backends (Postgres, SQLite, Redis)
- Parallel step execution in the orchestrator (with failure isolation)
- Rate limiting and timeout controls per capability
- Approval flows: steps that pause pending external confirmation

---

## Phase 4 — TUI (future)

A standalone terminal UI for monitoring and operating a running Conductor instance.

**Stack:** Go + [Bubble Tea](https://github.com/charmbracelet/bubbletea)

Scope (tentative):
- Live task queue and status board
- Workflow execution trace (step-by-step result view)
- Capability registry browser
- Log tail with filtering

**Why a separate binary:**
- Conductor Engine is a Python library and CLI tool — the TUI has no reason to share the runtime process
- Go compiles to a single static binary with no interpreter dependency, making it easy to distribute alongside the Python package
- Bubble Tea is purpose-built for this kind of interactive terminal work

**Target:** After Phase 3 — when the HTTP API and stable event model exist to feed the UI without polling hacks.

---

## Phase 5 — Autonomous Operation

The platform enforces its own rules and recovers without a human present.

- **Human-in-the-loop as a mode, not a requirement** — tasks, direction, and approvals can come from humans or from upstream systems. The engine does not stall waiting for human input unless explicitly configured to.
- **Behavioral retry and recovery** — failure is not just retried mechanically. The platform logs failure context, adjusts subsequent attempts, and escalates after threshold breaches.
- **Self-enforcing guardrails** — OPA integration at the supervisor level. Policies are evaluated before capability execution, not just at input validation. Deny decisions produce structured audit records.
- **Sandboxed execution** — capability execution runs in isolated contexts; filesystem and network capabilities are constrained by policy, not just by code.
- **Audit trail** — every task decision (allow, deny, retry, escalate) is recorded with enough context to reconstruct what happened and why.

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

- **Remote-first HTTP API** — the supervisor exposes a stable REST API. The CLI becomes a thin client over it. Local and remote operation are identical from the caller's perspective.
- **Authentication and authorization** — API calls require auth. OPA policies govern what callers can submit (which capabilities, which inputs, under what conditions).
- **Multi-tenant isolation** — separate capability registries, task stores, and guardrail policies per tenant.
- **Efficient resource management** — capability concurrency limits, queue depth controls, backpressure when the system is under load.
- **Deployment targets** — single binary (via a thin Go wrapper or containerized Python), `systemd` unit, Docker image, Kubernetes operator pattern.
- **Protected by default** — no capability executes without a policy allow decision. Default-deny with explicit permit grants.

This is the "OpenClaw-style but more protected and efficient" target — a hardened, remotely-operated orchestration platform with policy enforcement and a learning layer.

---

## Out of scope (explicitly)

These belong in programs built *on top of* Conductor, not inside it:

| Item | Why |
|---|---|
| LLM-backed planner | Domain concern — implement `PlannerContext`/`PlanResponse` externally |
| Distributed task queues (Redis, Celery) | Infrastructure — compose it in, don't embed it |
| Persistent workflow state across restarts | Downstream storage concern until Phase 3 defines the store interface |
| Copilot / agent framework | Conductor is the substrate; agents are consumers |
| UI beyond the TUI | Web dashboard is an integration, not a platform primitive |
