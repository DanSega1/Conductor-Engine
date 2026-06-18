---
name: passthrough-validator
description: Always passes validation — accepts any set of completed TaskRecords. Suitable for workflows without post-execution validation needs.
mode: subagent
engine_ref: engine/workflow/agents/passthrough_validator.py::PassthroughValidator
events_ref: docs/guild/EDGE_EVENTS.md
---

- Return passed=true and verdict='validation passed' for any workflow with all steps completed or partial.
- Do not inspect task outputs. Do not fail workflows.
- Override this stub with a real ValidatorInterface implementation for production use.
