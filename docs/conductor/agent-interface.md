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
