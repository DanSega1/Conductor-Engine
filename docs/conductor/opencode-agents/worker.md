# Worker Agent

**Config:** `.opencode/agents/worker/worker.json`
**Engine ref:** `engine/interfaces/workflow.py::WorkerInterface`
**Priority:** 3
**Role:** Turns PlanSteps into concrete TaskSubmissions.

## Purpose

The worker receives a `PlanStep` (name, capability, input_hint) and prior execution results, then refines the advisory `input_hint` into a concrete `TaskSubmission`. It does NOT execute capabilities — it returns the submission for the supervisor to execute. This is the bridge between "what to do" (planner) and "do it" (supervisor).

## Invariants

- Does NOT execute capabilities. Returns submissions for supervisor dispatch.
- Each TaskSubmission references a capability key that exists in the registry.
- Relational steps use `prior_results` to inform the next submission.

## Subagents

| Subagent | Engine ref | Risk | Purpose |
|---|---|---|---|
| passthrough-worker | `engine/workflow/agents/passthrough_worker.py` | — | Passes input_hint directly as submission input. |
| echo-capability | `engine/capabilities/echo.py` | low | Echoes input as output. Smoke tests. |
| filesystem-capability | `engine/capabilities/filesystem.py` | high | write_text, read_text, list_dir, delete, exists. Path-protected. |
| http-capability | `engine/capabilities/http.py` | medium | GET, POST, PUT, DELETE. Headers, JSON, params, timeout. |
| memory-capability | `engine/capabilities/memory.py` | low | In-memory KV store. get, set, delete, list, clear, search. |
| mcp-capability | `engine/capabilities/mcp.py` | medium | MCP executor wrapper. Transport in conductor-mcp addon. |

## Execution contract

```
WorkerContext(workflow_id, step=PlanStep, prior_results=[TaskRecord, ...])
  → work(step_name, context)
  → WorkerResponse(submission=TaskSubmission(...))
```

## Risk levels

| Level | Capabilities |
|---|---|
| low | echo, memory |
| medium | http, mcp |
| high | filesystem |

Risk level feeds into the policy engine (risk-level-policy can deny tasks above a configured threshold).

## When to use

- In workflow execution, between planning and supervisor dispatch
- When input hints from the planner need refinement with prior context
- To chain outputs from one step as inputs to the next
