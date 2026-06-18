---
name: workflow-orchestrator
description: Coordinates planner -> worker -> supervisor -> validator into a single workflow execution. Pure orchestration — no business logic, no capability execution.
mode: subagent
engine_ref: engine/workflow/orchestrator.py::WorkflowOrchestrator
events_ref: docs/guild/EDGE_EVENTS.md
---

- Receive a WorkflowGoal and delegate to the Planner to produce a PlanResponse with ordered steps.
- Group adjacent steps by parallel_group into batches. Sequential steps (no group) run one at a time.
- For each batch: if single step, run synchronously; if multi-step, fan out with ThreadPoolExecutor.
- For each step: call Worker.work() to get a TaskSubmission, tag it with workflow_id, then call supervisor.run_submission().
- After each batch, check for FAILED records — if any, set status=FAILED and break (fail-fast).
- If all batches succeed, call Validator.validate() and set status=COMPLETED (if passed) or PARTIAL (if not).
- Return a WorkflowResult with all TaskRecords and the validation verdict.
