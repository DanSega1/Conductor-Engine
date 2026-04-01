"""Tests for WorkflowOrchestrator — Phase 2, Step 2.

WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal) -> WorkflowResult

Flow under test:
  1. Planner.plan(goal_str, PlannerContext) → PlanResponse(steps)
  2. For each step: Worker.work(step_name, WorkerContext) → WorkerResponse(submission)
  3. supervisor.run_submission(submission) → TaskRecord
  4. Any FAILED record → fail-fast, status=FAILED, skip validator
  5. All passed → Validator.validate(goal_str, ValidatorContext) → ValidationResponse
  6. validation.passed → COMPLETED, else PARTIAL
  7. WorkflowResult(workflow_id=goal.workflow_id, ...)
"""

from __future__ import annotations

from pathlib import Path

from engine.interfaces.task import TaskRecord, TaskResult, TaskStatus, TaskSubmission
from engine.interfaces.workflow import (
    PlannerContext,
    PlanResponse,
    PlanStep,
    ValidationResponse,
    ValidatorContext,
    WorkerContext,
    WorkerResponse,
    WorkflowGoal,
    WorkflowStatus,
)
from engine.loader import load_capabilities
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor
from engine.workflow.orchestrator import WorkflowOrchestrator

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_supervisor(tmp_path: Path) -> TaskSupervisor:
    registry = load_capabilities(base_path=tmp_path)
    store = MemoryTaskStore()
    return TaskSupervisor(registry=registry, store=store, workdir=tmp_path)


def _echo_step(name: str = "say hello") -> PlanStep:
    return PlanStep(name=name, capability="echo", input_hint={"message": "hello"})


# ---------------------------------------------------------------------------
# Stub implementations of role interfaces
# ---------------------------------------------------------------------------


class StubPlanner:
    """Returns a fixed plan regardless of goal text."""

    def __init__(self, steps: list[PlanStep]) -> None:
        self._steps = steps

    def plan(self, goal: str, context: PlannerContext) -> PlanResponse:
        return PlanResponse(steps=self._steps)


class CapturingWorker:
    """Echoes the step's input_hint back as a TaskSubmission; records every WorkerContext."""

    def __init__(self) -> None:
        self.received_contexts: list[WorkerContext] = []

    def work(self, step_name: str, context: WorkerContext) -> WorkerResponse:
        self.received_contexts.append(context)
        return WorkerResponse(
            submission=TaskSubmission(
                name=step_name,
                capability=context.step.capability,
                input=context.step.input_hint,
            )
        )


class CapturingValidator:
    """Records ValidatorContexts it sees; returns a configurable pass/fail verdict."""

    def __init__(self, *, passed: bool = True, verdict: str = "ok") -> None:
        self._passed = passed
        self._verdict = verdict
        self.received_contexts: list[ValidatorContext] = []

    def validate(self, goal: str, context: ValidatorContext) -> ValidationResponse:
        self.received_contexts.append(context)
        return ValidationResponse(passed=self._passed, verdict=self._verdict)


class FailingTaskSupervisor:
    """Stub supervisor that always returns a FAILED TaskRecord without touching a real registry."""

    def run_submission(self, submission: TaskSubmission) -> TaskRecord:
        return TaskRecord(
            name=submission.name,
            capability=submission.capability,
            input=submission.input,
            status=TaskStatus.FAILED,
            result=TaskResult(success=False, error="stub: forced failure"),
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_orchestrator_runs_single_step_workflow(tmp_path: Path) -> None:
    planner = StubPlanner([_echo_step()])
    worker = CapturingWorker()
    validator = CapturingValidator()
    supervisor = _make_supervisor(tmp_path)
    goal = WorkflowGoal(goal="say hello")

    result = WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.records) == 1
    assert result.records[0].status == TaskStatus.COMPLETED


def test_orchestrator_result_uses_goal_workflow_id(tmp_path: Path) -> None:
    planner = StubPlanner([_echo_step()])
    worker = CapturingWorker()
    validator = CapturingValidator()
    supervisor = _make_supervisor(tmp_path)
    goal = WorkflowGoal(goal="id propagation check")

    result = WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert result.workflow_id == goal.workflow_id


def test_orchestrator_fails_fast_on_failed_task() -> None:
    # Two-step plan; supervisor returns FAILED on first step — second step must be skipped.
    planner = StubPlanner([_echo_step("step-1"), _echo_step("step-2")])
    worker = CapturingWorker()
    validator = CapturingValidator()
    supervisor = FailingTaskSupervisor()
    goal = WorkflowGoal(goal="fail fast")

    result = WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert result.status == WorkflowStatus.FAILED
    # Only the first record reaches the collector before the fail-fast short-circuit.
    assert len(result.records) == 1
    assert not validator.received_contexts


def test_orchestrator_calls_validator_after_all_steps_pass(tmp_path: Path) -> None:
    planner = StubPlanner([_echo_step()])
    worker = CapturingWorker()
    validator = CapturingValidator()
    supervisor = _make_supervisor(tmp_path)
    goal = WorkflowGoal(goal="validate when done")

    WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert len(validator.received_contexts) == 1
    assert validator.received_contexts[0].workflow_id == goal.workflow_id


def test_orchestrator_marks_partial_when_validation_fails(tmp_path: Path) -> None:
    planner = StubPlanner([_echo_step()])
    worker = CapturingWorker()
    validator = CapturingValidator(passed=False, verdict="output was insufficient")
    supervisor = _make_supervisor(tmp_path)
    goal = WorkflowGoal(goal="partial outcome")

    result = WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert result.status == WorkflowStatus.PARTIAL
    assert result.verdict is not None
    assert result.verdict.verdict == "output was insufficient"


def test_orchestrator_accumulates_prior_results(tmp_path: Path) -> None:
    step_a = PlanStep(name="step-a", capability="echo", input_hint={"message": "a"})
    step_b = PlanStep(name="step-b", capability="echo", input_hint={"message": "b"})
    planner = StubPlanner([step_a, step_b])
    worker = CapturingWorker()
    validator = CapturingValidator()
    supervisor = _make_supervisor(tmp_path)
    goal = WorkflowGoal(goal="two steps")

    WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert len(worker.received_contexts) == 2
    # First step sees an empty prior_results list.
    assert worker.received_contexts[0].prior_results == []
    # Second step's prior_results contains the first step's completed record.
    assert len(worker.received_contexts[1].prior_results) == 1
    assert worker.received_contexts[1].prior_results[0].name == "step-a"


def test_orchestrator_skips_validator_on_failure() -> None:
    planner = StubPlanner([_echo_step()])
    worker = CapturingWorker()
    validator = CapturingValidator()
    supervisor = FailingTaskSupervisor()
    goal = WorkflowGoal(goal="single failing step")

    result = WorkflowOrchestrator(planner, worker, validator, supervisor).run(goal)

    assert result.status == WorkflowStatus.FAILED
    assert validator.received_contexts == []
