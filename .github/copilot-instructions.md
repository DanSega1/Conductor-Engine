# Conductor Engine — Copilot Architecture Prompt

## Purpose

You are contributing to Conductor Engine, a minimal, composable orchestration runtime.

Your goal is to implement features that maintain:
- simplicity
- durability
- observability
- extensibility

This is not a task runner.
This is a control plane for workflows and systems.

---

## Core Mental Model

Conductor Engine is similar to:
- Kubernetes (control plane)
- Temporal / Netflix Conductor (durable workflows)
- Airflow (task orchestration)

But: **AI is optional — orchestration is the core.**

---

## Core Responsibilities

The system must:
- orchestrate tasks and workflows
- execute capabilities (tools)
- persist state at every step
- recover from failure
- expose full execution visibility

---

## Non-Negotiable Principles

### 1. Durable Execution (CRITICAL)

The system MUST guarantee:
- every task state is persisted
- execution can resume after crash/restart
- workflows survive long-running pauses
- retries are state-aware (not blind)

Durable execution is required for reliable systems.

### 2. Full State Visibility

The system must NEVER be a black box.

Every task must have:
- current state
- execution history
- inputs and outputs
- failure reason (if any)

### 3. Extensibility

Everything must be pluggable:
- orchestrators
- capabilities
- storage backends
- policy engines
- agents

Do NOT hardcode behavior.

### 4. AI is Optional

Valid execution path:

```text
Task → Capability → Result
```

Agents enhance the system but are NOT required.

### 5. Separation of Concerns

Strict layer boundaries:

| Layer | Responsibility |
|---|---|
| Orchestrator | controls workflow execution |
| Supervisor | executes individual tasks |
| Capability | performs the action |
| Guardrails | validate inputs |
| Policy Engine | authorize execution |

---

## Architecture

```text
Task
 ↓
Orchestrator
 ↓
Supervisor
 ↓
Guardrails
 ↓
Policy Engine
 ↓
Capability
 ↓
State Store
```

---

## Core Components

### Task Model

```python
class Task:
    id: str
    goal: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    input: dict
    result: dict
    history: list
```

### Capability Interface

```python
class Capability:
    name: str
    risk_level: str

    def execute(self, payload, context):
        pass
```

Capabilities must be:
- stateless
- idempotent (or declare side effects explicitly)

### Orchestrator Interface

The orchestrator MUST be replaceable.

```python
class Orchestrator:
    def run(self, workflow):
        pass
```

Implementations:
- `LinearOrchestrator` — default, sequential steps
- `ParallelOrchestrator` — future
- `DAGOrchestrator` — future
- `AgentOrchestrator` — future

### Supervisor

- validates tasks
- executes capabilities
- persists results

Must NOT contain workflow logic. The supervisor (`engine/supervisor/service.py`) is the single source of task execution truth — no capability or agent should bypass it.

### Guardrails

- validate structure and schema
- prevent invalid execution
- run before a task leaves PENDING

### Policy Engine

- authorize execution
- enforce permissions
- deny unsafe operations

---

## Execution Model

**Minimal:**

```text
Submit Task → Supervisor → Capability → Store Result
```

**Workflow:**

```text
Goal → Orchestrator → Step Execution → Validation → Result
```

---

## Workflow Patterns (must support)

- **Sequential** — default, ordered steps
- **Parallel** — independent steps run concurrently
- **Conditional** — branching based on step output
- **Loop** — retry and refinement cycles

Do NOT assume linear-only execution.

---

## State and Persistence

- state must be persisted after each step
- no in-memory-only critical state
- system must be able to resume execution after restart
- storage is pluggable — Postgres, SQLite, Redis, filesystem
- Pydantic v2 — validate at system boundaries, not deep inside execution logic

---

## Event Model

The system should emit structured events:
- `task_started`
- `task_completed`
- `task_failed`

Used for: logging, metrics, TUI, integrations.

---

## Reliability Features

The system must support:
- retries with attempt tracking (`max_retries`, `attempt` on `TaskRecord`)
- timeouts (to avoid stuck workflows)
- backpressure
- rate limits per capability

---

## Failure Handling

Failures must:
- be recorded with full context (error, attempt count, timestamps)
- support state-aware retry (not blind repetition)
- allow escalation after threshold

Future:
- compensation / rollback (Phase 5+)
- guild-level failure sharing across projects (Phase 6)

---

## Testing Philosophy

Every component must be:
- testable in isolation
- deterministic (no hidden side effects)
- mockable at system boundaries

---

## Anti-Patterns (do not do)

- Tightly coupling to any LLM provider
- Embedding business logic in core
- Assuming single-node runtime
- Relying on in-memory-only state for critical data
- Hiding execution state from callers
- Bypassing the supervisor from a capability or agent

---

## Instructions for Copilot

When generating code:

- Follow interfaces strictly — `engine/interfaces/` defines the contracts
- Prefer composition over inheritance
- Keep functions small and readable
- Avoid unnecessary abstractions
- Ensure components are replaceable without touching the supervisor
- The supervisor (`engine/supervisor/service.py`) is the single source of orchestration truth — no capability or agent should bypass it
- Pydantic v2 — validate at system boundaries, not deep inside execution logic
- Every piece of code should increase modularity, reduce coupling, improve clarity, and support extensibility

---

## Contribution Goal

Every contribution must:
- improve modularity
- preserve durability guarantees
- maintain system observability
- keep the core minimal

---

## Final Rule

> Build a durable, observable orchestration engine — not a feature-rich tool.
