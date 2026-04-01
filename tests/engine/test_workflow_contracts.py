"""Tests for engine/interfaces/workflow.py contracts."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from engine.interfaces.task import TaskRecord, TaskStatus, TaskSubmission
from engine.interfaces.workflow import (
    PlannerContext,
    PlannerInterface,
    PlanResponse,
    PlanStep,
    ValidationResponse,
    ValidatorContext,
    ValidatorInterface,
    WorkerContext,
    WorkerInterface,
    WorkerResponse,
    WorkflowGoal,
    WorkflowResult,
    WorkflowStatus,
)

# ---------------------------------------------------------------------------
# Model construction and defaults
# ---------------------------------------------------------------------------


def test_workflow_goal_defaults() -> None:
    goal = WorkflowGoal(goal="do something")
    assert goal.workflow_id
    assert goal.capabilities == []
    assert goal.metadata == {}


def test_plan_step_construction() -> None:
    step = PlanStep(name="fetch", capability="http")
    assert step.input_hint == {}


def test_plan_response_construction() -> None:
    step = PlanStep(name="s1", capability="echo")
    resp = PlanResponse(steps=[step])
    assert resp.rationale == ""
    assert len(resp.steps) == 1


def test_worker_context_defaults() -> None:
    step = PlanStep(name="s", capability="echo")
    ctx = WorkerContext(workflow_id="wf-1", step=step)
    assert ctx.prior_results == []


def test_worker_response_construction() -> None:
    submission = TaskSubmission(name="t", capability="echo")
    resp = WorkerResponse(submission=submission)
    assert resp.submission.capability == "echo"


def test_planner_context_defaults() -> None:
    ctx = PlannerContext(workflow_id="wf-1", goal="plan this")
    assert ctx.capabilities == []


def test_validator_context_defaults() -> None:
    ctx = ValidatorContext(workflow_id="wf-1", goal="check this")
    assert ctx.results == []


def test_workflow_result_defaults() -> None:
    result = WorkflowResult(
        goal="accomplish X",
        status=WorkflowStatus.PENDING,
    )
    assert result.workflow_id
    assert result.records == []
    assert result.verdict is None


# ---------------------------------------------------------------------------
# workflow_id uniqueness
# ---------------------------------------------------------------------------


def test_workflow_goal_unique_ids() -> None:
    a = WorkflowGoal(goal="first")
    b = WorkflowGoal(goal="second")
    assert a.workflow_id != b.workflow_id


def test_workflow_result_unique_ids() -> None:
    a = WorkflowResult(goal="first", status=WorkflowStatus.PENDING)
    b = WorkflowResult(goal="second", status=WorkflowStatus.PENDING)
    assert a.workflow_id != b.workflow_id


# ---------------------------------------------------------------------------
# PlanStep.input_hint is advisory — WorkerResponse may differ
# ---------------------------------------------------------------------------


def test_worker_response_input_may_differ_from_hint() -> None:
    step = PlanStep(name="fetch", capability="http", input_hint={"url": "https://example.com"})
    submission = TaskSubmission(
        name="fetch",
        capability="http",
        input={"url": "https://override.example.com", "method": "POST"},
    )
    ctx = WorkerContext(workflow_id="wf-1", step=step)
    resp = WorkerResponse(submission=submission)
    # No error — input_hint is advisory only
    assert resp.submission.input["url"] != ctx.step.input_hint["url"]


# ---------------------------------------------------------------------------
# WorkflowResult with multiple records
# ---------------------------------------------------------------------------


def test_workflow_result_with_records() -> None:
    records = [
        TaskRecord(name=f"task-{i}", capability="echo", status=TaskStatus.COMPLETED)
        for i in range(3)
    ]
    result = WorkflowResult(
        goal="run three tasks",
        status=WorkflowStatus.COMPLETED,
        records=records,
    )
    assert len(result.records) == 3


# ---------------------------------------------------------------------------
# Protocol isinstance checks
# ---------------------------------------------------------------------------


def test_planner_interface_isinstance() -> None:
    class MockPlanner:
        def plan(self, goal: str, context: PlannerContext) -> PlanResponse:
            return PlanResponse(steps=[])

    assert isinstance(MockPlanner(), PlannerInterface)


def test_worker_interface_isinstance() -> None:
    class MockWorker:
        def work(self, step_name: str, context: WorkerContext) -> WorkerResponse:
            return WorkerResponse(
                submission=TaskSubmission(name=step_name, capability="echo")
            )

    assert isinstance(MockWorker(), WorkerInterface)


def test_validator_interface_isinstance() -> None:
    class MockValidator(ValidatorInterface):
        def validate(self, goal: str, context: ValidatorContext) -> ValidationResponse:
            return ValidationResponse(passed=True, verdict="ok")

    assert isinstance(MockValidator(), ValidatorInterface)


def test_validator_interface_cannot_instantiate_directly() -> None:
    with pytest.raises(TypeError):
        ValidatorInterface()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# WorkflowStatus enum values
# ---------------------------------------------------------------------------


def test_workflow_status_all_values() -> None:
    assert WorkflowStatus.PENDING
    assert WorkflowStatus.RUNNING
    assert WorkflowStatus.COMPLETED
    assert WorkflowStatus.FAILED
    assert WorkflowStatus.PARTIAL


# ---------------------------------------------------------------------------
# ValidationResponse defaults
# ---------------------------------------------------------------------------


def test_validation_response_issues_default_empty() -> None:
    resp = ValidationResponse(passed=True, verdict="all good")
    assert resp.issues == []


def test_validation_response_with_issues() -> None:
    resp = ValidationResponse(passed=False, verdict="failed", issues=["missing output"])
    assert len(resp.issues) == 1


# ---------------------------------------------------------------------------
# Pydantic validation errors
# ---------------------------------------------------------------------------


def test_plan_step_requires_name() -> None:
    with pytest.raises(ValidationError):
        PlanStep(capability="echo")  # type: ignore[call-arg]


def test_plan_step_requires_capability() -> None:
    with pytest.raises(ValidationError):
        PlanStep(name="step-1")  # type: ignore[call-arg]
