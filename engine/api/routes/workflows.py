"""Workflow routes.

Endpoints
---------
POST  /v1/workflows               Submit and run a workflow
GET   /v1/workflows/{workflow_id} Get workflow trace (all tasks for that workflow)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from engine.api.dependencies import SupervisorDep, get_orchestrator
from engine.control_plane.contracts import ControlPlaneWorkflowTraceV1
from engine.interfaces.workflow import WorkflowGoal

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Submit and run a workflow
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=200,
    summary="Submit and run a workflow",
    response_model=dict,
    responses={
        200: {"description": "Workflow completed — full trace returned"},
        400: {"description": "Invalid workflow goal"},
        501: {"description": "Workflow orchestrator not configured"},
    },
)
def run_workflow(
    body: WorkflowGoal,
    supervisor: SupervisorDep,
    orchestrator: Annotated[object, Depends(get_orchestrator)],
):
    """Submit a workflow goal and run it through the planner → worker → validator pipeline.

    Returns the full execution trace including per-step task records.

    Example request:
    ```json
    {
      "goal": "Echo two messages",
      "capabilities": ["echo"],
      "metadata": {}
    }
    ```

    Example response:
    ```json
    {
      "workflow_id": "...",
      "status": "completed",
      "tasks": [
        {"task_id": "...", "name": "step-1", "status": "completed", ...}
      ]
    }
    ```
    """
    try:
        result = orchestrator.run(body)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail={"code": "workflow_failed", "message": str(exc)}) from exc

    # Build trace from result records
    records = result.records
    trace = ControlPlaneWorkflowTraceV1.from_records(body.workflow_id, records)
    return trace.model_dump()


# ---------------------------------------------------------------------------
# Get workflow trace
# ---------------------------------------------------------------------------


@router.get(
    "/{workflow_id}",
    summary="Get workflow trace",
    response_model=dict,
    responses={
        200: {"description": "Workflow trace with all task steps"},
        404: {"description": "No tasks found for this workflow ID"},
    },
)
def get_workflow_trace(workflow_id: str, supervisor: SupervisorDep):
    """Return the execution trace for a workflow — all tasks that share the workflow ID.

    Useful for polling a running or completed workflow after it was submitted
    asynchronously, or for replaying its full step-by-step result history.
    """
    all_tasks = supervisor.list_tasks()
    workflow_tasks = [t for t in all_tasks if t.workflow_id == workflow_id]

    if not workflow_tasks:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"No tasks found for workflow {workflow_id!r}"},
        )

    trace = ControlPlaneWorkflowTraceV1.from_records(workflow_id, workflow_tasks)
    return trace.model_dump()
