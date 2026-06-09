"""Task management routes.

Endpoints
---------
GET    /v1/tasks                      List tasks with pagination and status filter
POST   /v1/tasks                      Submit a task (enqueue, returns 202)
POST   /v1/tasks/run                  Submit and execute inline (returns 200)
GET    /v1/tasks/{task_id}            Get a single task by ID
POST   /v1/tasks/{task_id}/run        Execute a queued/pending task now
POST   /v1/tasks/{task_id}/approve    Approve a task awaiting approval
POST   /v1/tasks/{task_id}/cancel     Cancel a task awaiting approval
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from engine.api.dependencies import AuthDep, SupervisorDep
from engine.api.models import ApproveTaskRequest, CancelTaskRequest, PageMeta, SubmitTaskRequest
from engine.control_plane.contracts import ControlPlaneTaskV1
from engine.interfaces.task import TaskStatus, TaskSubmission

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_v1(task) -> ControlPlaneTaskV1:
    return ControlPlaneTaskV1.from_task(task)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="List tasks",
    response_model=dict,
    responses={200: {"description": "Paginated list of tasks"}},
)
def list_tasks(
    supervisor: SupervisorDep,
    status: Annotated[str | None, Query(description="Filter by task status")] = None,
    limit: Annotated[int | None, Query(ge=1, le=1000, description="Max results")] = 50,
    offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
):
    """Return a paginated list of tasks, optionally filtered by status.

    **Status values:** ``pending``, ``running``, ``completed``, ``failed``,
    ``awaiting_approval``, ``approved``, ``policy_denied``, ``cancelled``, ``escalated``

    Example response:
    ```json
    {
      "items": [...],
      "meta": {"limit": 50, "offset": 0, "total": 3}
    }
    ```
    """
    if status is not None:
        try:
            TaskStatus(status)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_status", "message": f"Unknown status: {status!r}"},
            ) from exc

    all_tasks = supervisor.list_tasks(status=status)
    page = all_tasks[offset : offset + limit] if limit is not None else all_tasks[offset:]

    return {
        "items": [_to_v1(t).model_dump() for t in page],
        "meta": PageMeta(limit=limit, offset=offset, total=len(all_tasks)).model_dump(),
    }


# ---------------------------------------------------------------------------
# Submit (async enqueue)
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=202,
    summary="Submit a task",
    response_model=dict,
    responses={
        202: {"description": "Task accepted and enqueued"},
        400: {"description": "Invalid submission"},
    },
)
def submit_task(body: SubmitTaskRequest, supervisor: SupervisorDep, auth: AuthDep):
    """Submit a task for asynchronous execution.

    The task is created in ``PENDING`` state and added to the work queue.
    Use ``POST /v1/tasks/run`` to submit and execute inline instead.

    Example request:
    ```json
    {
      "name": "Echo hello",
      "capability": "echo",
      "input": {"message": "hello"},
      "max_retries": 2
    }
    ```
    """
    submission = TaskSubmission(
        name=body.name,
        capability=body.capability,
        input=body.input,
        metadata={**body.metadata, "submitted_by": auth.actor},
        max_retries=body.max_retries,
        workflow_id=body.workflow_id,
    )
    try:
        task = supervisor.submit(submission)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail={"code": "submit_failed", "message": str(exc)}) from exc
    return _to_v1(task).model_dump()


# ---------------------------------------------------------------------------
# Submit + run inline
# ---------------------------------------------------------------------------


@router.post(
    "/run",
    status_code=200,
    summary="Submit and run a task inline",
    response_model=dict,
    responses={
        200: {"description": "Task completed (or failed) — full result returned"},
        400: {"description": "Invalid submission"},
    },
)
def run_task_inline(body: SubmitTaskRequest, supervisor: SupervisorDep, auth: AuthDep):
    """Submit a task and execute it synchronously before returning.

    The response contains the final task state including result and audit trail.
    Use ``POST /v1/tasks`` for non-blocking enqueueing.
    """
    submission = TaskSubmission(
        name=body.name,
        capability=body.capability,
        input=body.input,
        metadata={**body.metadata, "submitted_by": auth.actor},
        max_retries=body.max_retries,
        workflow_id=body.workflow_id,
    )
    try:
        task = supervisor.run_submission(submission)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail={"code": "submit_failed", "message": str(exc)}) from exc
    return _to_v1(task).model_dump()


# ---------------------------------------------------------------------------
# Get single task
# ---------------------------------------------------------------------------


@router.get(
    "/{task_id}",
    summary="Get a task",
    response_model=dict,
    responses={
        200: {"description": "Task record"},
        404: {"description": "Task not found"},
    },
)
def get_task(task_id: str, supervisor: SupervisorDep):
    """Return the full task record including result and audit trail."""
    try:
        task = supervisor.get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"Task {task_id!r} not found"}) from exc
    return _to_v1(task).model_dump()


# ---------------------------------------------------------------------------
# Run a queued task now
# ---------------------------------------------------------------------------


@router.post(
    "/{task_id}/run",
    summary="Run a queued task",
    response_model=dict,
    responses={
        200: {"description": "Task executed — result returned"},
        404: {"description": "Task not found"},
    },
)
def run_queued_task(task_id: str, supervisor: SupervisorDep):
    """Execute a task that is currently in PENDING or APPROVED state.

    Useful when a task was submitted with ``POST /v1/tasks`` (enqueue only)
    and you want to drive execution explicitly rather than relying on the
    background queue drainer.
    """
    try:
        task = supervisor.run_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    return _to_v1(task).model_dump()


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


@router.post(
    "/{task_id}/approve",
    summary="Approve a task",
    response_model=dict,
    responses={
        200: {"description": "Task approved (and optionally executed)"},
        400: {"description": "Task is not awaiting approval"},
        404: {"description": "Task not found"},
    },
)
def approve_task(task_id: str, body: ApproveTaskRequest, supervisor: SupervisorDep, auth: AuthDep):
    """Approve a task that is in ``awaiting_approval`` state.

    Set ``run: true`` (default) to execute the task immediately after approval.
    Set ``run: false`` to approve and re-enqueue for later execution.

    Example request:
    ```json
    {"actor": "ops-engineer", "run": true}
    ```
    """
    try:
        task = supervisor.approve_task(
            task_id,
            actor=body.actor or auth.actor,
            metadata=body.metadata,
            run=body.run,
        )
    except ValueError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail={"code": "approve_failed", "message": msg}) from exc
    return _to_v1(task).model_dump()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@router.post(
    "/{task_id}/cancel",
    summary="Cancel a task",
    response_model=dict,
    responses={
        200: {"description": "Task cancelled"},
        400: {"description": "Task cannot be cancelled from its current state"},
        404: {"description": "Task not found"},
    },
)
def cancel_task(task_id: str, body: CancelTaskRequest, supervisor: SupervisorDep, auth: AuthDep):
    """Cancel a task that is in ``awaiting_approval`` state.

    The task transitions to ``cancelled`` with the provided reason recorded
    in the audit trail.
    """
    try:
        task = supervisor.cancel_task(
            task_id,
            actor=body.actor or auth.actor,
            reason=body.reason,
            metadata=body.metadata,
        )
    except ValueError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail={"code": "cancel_failed", "message": msg}) from exc
    return _to_v1(task).model_dump()
