"""Workflow contracts for the Conductor Engine orchestration layer.

Defines the shared models and Protocol interfaces used across the planner,
worker, and validator roles.  These types sit above the task layer — a workflow
is composed of one or more TaskSubmissions executed by the supervisor.

Import hierarchy (no circular deps):
    workflow.py → task.py (TaskSubmission, TaskRecord)
    workflow.py does NOT import agent.py
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field

from engine.interfaces.task import TaskRecord, TaskSubmission

# ---------------------------------------------------------------------------
# Shared enums and value types
# ---------------------------------------------------------------------------


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class PlanStep(BaseModel):
    """One step inside a planner-generated plan.

    ``input_hint`` is advisory: the worker refines it into a concrete
    ``TaskSubmission`` before handing off to the supervisor.
    """

    name: str
    capability: str
    input_hint: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level workflow input / output
# ---------------------------------------------------------------------------


class WorkflowGoal(BaseModel):
    """The input submitted to start an orchestrated workflow."""

    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowResult(BaseModel):
    """Final assembled result of a completed workflow run.

    ``records`` holds task-level execution history in memory.
    ``verdict`` is populated when a ValidatorInterface has run over the results.
    """

    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    records: list[TaskRecord] = Field(default_factory=list)
    verdict: ValidationResponse | None = None


# ---------------------------------------------------------------------------
# Planner role
# ---------------------------------------------------------------------------


class PlannerContext(BaseModel):
    """Context supplied to a planner when generating a plan."""

    workflow_id: str
    goal: str
    capabilities: list[str] = Field(default_factory=list)


class PlanResponse(BaseModel):
    """The planner's output: an ordered list of steps and a rationale."""

    steps: list[PlanStep] = Field(default_factory=list)
    rationale: str = ""


@runtime_checkable
class PlannerInterface(Protocol):
    """Contract for any component that can turn a goal into a plan."""

    def plan(self, goal: str, context: PlannerContext) -> PlanResponse:
        """Produce an ordered execution plan for the supplied goal."""
        ...


# ---------------------------------------------------------------------------
# Worker role
# ---------------------------------------------------------------------------


class WorkerContext(BaseModel):
    """Context supplied to a worker when executing a single plan step."""

    workflow_id: str
    step: PlanStep
    prior_results: list[TaskRecord] = Field(default_factory=list)


class WorkerResponse(BaseModel):
    """The worker's output: a concrete TaskSubmission ready for the supervisor."""

    submission: TaskSubmission


@runtime_checkable
class WorkerInterface(Protocol):
    """Contract for any component that can turn a plan step into a TaskSubmission."""

    def work(self, step_name: str, context: WorkerContext) -> WorkerResponse:
        """Resolve a plan step into a concrete TaskSubmission."""
        ...


# ---------------------------------------------------------------------------
# Validator role
# ---------------------------------------------------------------------------


class ValidatorContext(BaseModel):
    """Context supplied to a validator when assessing workflow results."""

    workflow_id: str
    goal: str
    results: list[TaskRecord] = Field(default_factory=list)


class ValidationResponse(BaseModel):
    """Verdict produced by a ValidatorInterface over a completed workflow."""

    passed: bool
    verdict: str
    issues: list[str] = Field(default_factory=list)


@runtime_checkable
class ValidatorInterface(Protocol):
    """Contract for any component that can validate a completed workflow."""

    def validate(self, goal: str, context: ValidatorContext) -> ValidationResponse:
        """Assess whether the workflow results satisfy the original goal."""
        ...
