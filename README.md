# Conductor Engine

<p align="center">
  <a href="https://github.com/DanSega1/Conductor-Engine/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/DanSega1/Conductor-Engine/ci.yml?branch=main&logo=github&label=CI" alt="CI">
  </a>
  <a href="https://pypi.org/project/conductor-engine/">
    <img src="https://img.shields.io/pypi/v/conductor-engine.svg" alt="PyPI">
  </a>
  <a href="https://pypi.org/project/conductor-engine/">
    <img src="https://img.shields.io/pypi/pyversions/conductor-engine.svg" alt="Python versions">
  </a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/DanSega1/Conductor-Engine/main/docs/assets/conductor-engine-banner.png" alt="Conductor Engine banner" width="600">
</p>

A minimal, installable orchestration runtime for task execution, capability loading, guardrails, storage abstractions, and future agent and policy layers.

## AI Collaboration

This project is AI-enhanced. A significant portion of the code, tests, and documentation was written with AI assistance as part of an intentional human-AI collaborative workflow.

## Quick Start

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e .
cond run examples/echo.yaml
cond workflow run examples/workflow-echo.yaml
```

Use `man cond` for the stable CLI reference, `cond help` for runtime-aware command and capability help, and `cond --help` for standard flag usage.

## Architecture At A Glance

```mermaid
sequenceDiagram
    actor User
    participant CLI as cond workflow run
    participant ORCH as WorkflowOrchestrator
    participant PLAN as Planner
    participant WORK as Worker
    participant SUP as TaskSupervisor
    participant CAP as Capability
    participant STORE as TaskStore

    User->>CLI: workflow.yaml
    CLI->>ORCH: run(WorkflowGoal)
    ORCH->>PLAN: plan(goal, PlannerContext)
    PLAN-->>ORCH: PlanResponse(steps)

    loop for each PlanStep
        ORCH->>WORK: work(step_name, WorkerContext)
        WORK-->>ORCH: WorkerResponse(TaskSubmission)
        ORCH->>SUP: run_submission(submission)
        SUP->>CAP: validate_input -> execute
        CAP-->>SUP: CapabilityResult
        SUP->>STORE: save(TaskRecord)
        SUP-->>ORCH: TaskRecord
    end

    ORCH-->>CLI: WorkflowResult
```

## What You Get

- Generic task contracts and a supervisor runtime that stays small and composable.
- Built-in `echo`, `filesystem`, `http`, and optional `memory` capabilities.
- A workflow layer with planner, worker, and validator interfaces over the same supervisor path.
- Local JSON task storage and an in-memory queue for straightforward local operation.
- A `cond` CLI with task execution, workflow execution, capability discovery, dynamic help, and native manpage support.

## Docs And Examples

- [Examples](examples/README.md) for runnable tasks and workflows.
- [Roadmap](docs/conductor/roadmap.md) for phase planning and backlog tracking.
- [Architecture diagrams](docs/conductor/architecture-diagrams.md) for the full system view.
- [CLI reference](docs/conductor/cond-cli.md) for command-focused documentation.
- [PyPI project page](https://pypi.org/project/conductor-engine/) for published releases.

## Built With Conductor Engine

**[home-ai-control-plane](https://github.com/DanSega1/home-ai-control-plane)** is the motivating downstream system: a policy-governed, multi-agent AI control plane running on a Raspberry Pi 5 for personal digital workflows, home-lab services, and smart-home integrations.

See [the use case write-up](docs/conductor/use-cases/home-control-plane.md) for how the engine maps to that system.

## Development Notes

- Python support now targets `3.14+`.
- The repo convention is a single root virtualenv: `python3.14 -m venv .venv`.
- Coverage and license badges can be added once coverage reporting and license metadata are published in-repo.
