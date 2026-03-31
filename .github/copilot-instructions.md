# Conductor Engine — Copilot Prompt Guide

## Purpose

You are assisting in building **Conductor Engine**, a modular, AI-agnostic orchestration framework.

Your goal is to generate code that aligns with:

* clean architecture
* modular design
* pluggable components
* minimal core
* runtime agnosticism

---

## What Conductor Engine Is

Conductor Engine is:

> A control plane for orchestrating agents, capabilities, and systems.

It is **NOT**:

* just an AI agent framework
* not tied to any LLM provider
* not a monolithic automation tool

---

## Core Responsibilities

Conductor Engine must:

* orchestrate tasks
* coordinate agents (optional)
* execute capabilities (tools)
* enforce guardrails and policies
* remain storage and runtime agnostic

---

## Architecture Overview

```text
Task
 ↓
Supervisor (Orchestrator)
 ↓
Agent (optional)
 ↓
Guardrails (validation)
 ↓
Policy Engine (authorization)
 ↓
Capability Execution
 ↓
State Update
```

---

## Core Components

### 1. Supervisor (Core Orchestrator)

* manages task lifecycle
* routes execution
* coordinates agents and capabilities

### 2. Task Model

A task is the unit of execution.

```python
class Task:
    id: str
    goal: str
    status: str
    steps: list
    result: dict
```

### 3. Capability Interface

Capabilities are pluggable tools.

```python
class Capability:
    name: str
    risk_level: str

    def execute(self, payload, context):
        pass
```

### 4. Agent Interface (Optional Layer)

Agents provide reasoning, not execution.

```python
class Agent:
    name: str

    def plan(self, task):
        pass

    def evaluate(self, task):
        pass
```

### 5. Guardrails

Validate agent output before execution:

* schema validation
* tool filtering
* input sanitization

### 6. Policy Engine (OPA-like)

Policy enforces permissions.

```python
class PolicyEngine:
    def authorize(self, action, context):
        pass
```

### 7. Plugin System

Capabilities must be dynamically loadable.

```python
registry.register(capability)
```

### 8. Storage Abstraction

The framework must not depend on specific databases.

```python
class TaskStore:
    def create(self, task): pass
    def update(self, task): pass
    def get(self, id): pass
```

---

## Design Principles

### Keep Core Minimal

Only include:

* orchestration logic
* interfaces
* execution flow

### Everything is Pluggable

Do NOT hardcode:

* LLM providers
* databases
* external APIs
* integrations

### AI is Optional

The system must work without AI:

```text
Task → Capability → Result
```

AI is an enhancement, not a dependency.

### Separate Framework from Implementation

Framework: generic orchestration logic and interfaces.

Application (e.g., home-ai-control-plane): integrations, workflows, configs.

### Runtime Agnostic

Must support: local execution, Docker, Kubernetes, agent platforms.

### Storage Agnostic

Support via adapters: Postgres, Mongo, Redis/Valkey, filesystem.

### Simple First

Avoid: premature abstraction, unnecessary layers, complex patterns.

---

## Execution Model

Minimal flow:

```text
Submit Task → Supervisor → Execute Capability → Store Result
```

Advanced flow (Phase 2+):

```text
Task → Planner Agent → Execution → Validator Agent → Supervisor decision
```

---

## Extensibility

The system must allow adding new capabilities, agents, orchestrators, storage backends, and policy engines **without modifying core logic**.

---

## Anti-Patterns (Avoid)

* Tightly coupling to OpenAI or any provider
* Embedding business logic in core
* Mixing framework code with integration code
* Hardcoding workflows
* Assuming a single runtime environment

---

## Long-Term Vision

> A universal orchestration runtime for AI, automation, and distributed systems.
> Safe to run unattended. Remote-first. Policy-enforced. Self-improving over time.

Mental model:

```text
Kubernetes (control plane)  +  Zapier (automation)  +  LangChain (AI layer)
```

---

## Instructions for Copilot

When generating code:

* Follow interfaces strictly — `engine/interfaces/` defines the contracts
* Prefer composition over inheritance
* Keep functions small and readable
* Avoid unnecessary abstractions
* Ensure components are replaceable without touching the supervisor
* The supervisor (`engine/supervisor/service.py`) is the single source of orchestration truth — no capability or agent should bypass it
* Pydantic v2 — validate at system boundaries, not deep inside execution logic
* Every piece of code should increase modularity, reduce coupling, improve clarity, and support extensibility

> Build a foundation, not a feature.
