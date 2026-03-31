# Agent Interface

## Phase 1 Position

Agents are not required for the initial runtime loop, but the interface is defined now so the engine can grow into planner/worker/validator roles without reworking the package boundaries.

## Contract

### `AgentRole`

- `supervisor`
- `planner`
- `worker`
- `validator`

### `AgentInterface`

```python
class AgentInterface(Protocol):
    role: AgentRole

    def run(self, goal: str, context: AgentContext) -> AgentResponse:
        ...
```

## Intent

- The interface is logical, not model-specific.
- Implementations may be deterministic, LLM-backed, or remote.
- The supervisor owns orchestration; agents supply specialized decision-making.

## Near-Term Usage

- Phase 1: no runtime dependency on agents
- Phase 2: planner breaks goals into steps, worker executes capabilities, validator checks output

## Phase 2 Contract Design (decided)

The generic `AgentContext` / `AgentResponse` types are retained as base types but are not used as concrete runtime types in the orchestrator. Phase 2 introduces role-specific narrowed types:

- `PlannerContext` / `PlanResponse` — planner receives a goal and available capabilities; returns ordered steps
- `WorkerContext` / `WorkerResponse` — worker receives a step and prior results; returns a concrete `TaskSubmission`
- `ValidatorContext` / `ValidationResponse` — validator receives the goal and all completed `TaskRecord`s; returns a pass/fail verdict

These live in `engine/interfaces/workflow.py` (Phase 2). The supervisor (`engine/supervisor/service.py`) is not modified — the `WorkflowOrchestrator` sits above it.
