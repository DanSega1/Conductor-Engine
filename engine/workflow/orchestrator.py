"""WorkflowOrchestrator — Phase 2 orchestration layer.

Coordinates planner → worker → supervisor → validator into a single
workflow execution.  Pure orchestration: no business logic, no LLM calls,
no hardcoded behaviour.
"""

from __future__ import annotations

from engine.interfaces.task import TaskStatus
from engine.interfaces.workflow import (
    PlannerContext,
    PlannerInterface,
    ValidatorContext,
    ValidatorInterface,
    WorkerContext,
    WorkerInterface,
    WorkflowGoal,
    WorkflowResult,
    WorkflowStatus,
)
from engine.supervisor.service import TaskSupervisor


class WorkflowOrchestrator:
    """Orchestrates a workflow by delegating to planner, worker, and validator."""

    def __init__(
        self,
        planner: PlannerInterface,
        worker: WorkerInterface,
        validator: ValidatorInterface,
        supervisor: TaskSupervisor,
    ) -> None:
        self.planner = planner
        self.worker = worker
        self.validator = validator
        self.supervisor = supervisor

    def run(self, goal: WorkflowGoal) -> WorkflowResult:
        planner_context = PlannerContext(
            workflow_id=goal.workflow_id,
            goal=goal.goal,
            capabilities=goal.capabilities,
        )
        plan = self.planner.plan(goal.goal, planner_context)

        records = []
        status = WorkflowStatus.RUNNING

        for step in plan.steps:
            worker_context = WorkerContext(
                workflow_id=goal.workflow_id,
                step=step,
                prior_results=list(records),
            )
            response = self.worker.work(step.name, worker_context)
            record = self.supervisor.run_submission(response.submission)
            records.append(record)

            if record.status == TaskStatus.FAILED:
                status = WorkflowStatus.FAILED
                break

        verdict = None
        if status != WorkflowStatus.FAILED:
            validator_context = ValidatorContext(
                workflow_id=goal.workflow_id,
                goal=goal.goal,
                results=records,
            )
            validation = self.validator.validate(goal.goal, validator_context)
            verdict = validation
            status = WorkflowStatus.COMPLETED if validation.passed else WorkflowStatus.PARTIAL

        return WorkflowResult(
            workflow_id=goal.workflow_id,
            goal=goal.goal,
            status=status,
            records=records,
            verdict=verdict,
        )
