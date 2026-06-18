---
name: linear-planner
description: Generates ordered steps from a structured workflow goal. Deterministic — no LLM required.
mode: subagent
engine_ref: engine/workflow/agents/linear_planner.py::LinearPlanner
events_ref: docs/guild/EDGE_EVENTS.md
---

- Parse the workflow goal for explicit step declarations (capability + input hints).
- Return steps in declaration order. Do not reorder or infer implicit steps.
- If the goal declares parallel_group on adjacent steps, preserve the group assignment.
- This is a stub implementation for deterministic workflows. Override for LLM-backed planning.
