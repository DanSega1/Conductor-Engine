---
name: passthrough-worker
description: Resolves each PlanStep.input_hint directly as the TaskSubmission input without transformation.
mode: subagent
engine_ref: engine/workflow/agents/passthrough_worker.py::PassthroughWorker
events_ref: docs/guild/EDGE_EVENTS.md
---

- Take the PlanStep as-is. Use input_hint for the TaskSubmission input field.
- Do not transform or augment the input. This is a pure bridge from plan to submission.
- Suitable for workflows where the planner already produces fully-formed inputs.
