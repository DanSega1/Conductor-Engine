"""WorkflowOrchestrator — Phase 2 orchestration layer.

Coordinates planner → worker → supervisor → validator into a single
workflow execution.  Pure orchestration: no business logic, no LLM calls,
no hardcoded behaviour.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from engine.interfaces.task import TaskStatus
from engine.interfaces.workflow import (
    PlannerContext,
    PlannerInterface,
    PlanStep,
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

    def _run_step(
        self,
        *,
        step: PlanStep,
        workflow_id: str,
        prior_results: list,
    ):
        worker_context = WorkerContext(
            workflow_id=workflow_id,
            step=step,
            prior_results=list(prior_results),
        )
        response = self.worker.work(step.name, worker_context)
        submission = response.submission.model_copy(update={"workflow_id": workflow_id})
        return self.supervisor.run_submission(submission)

    @staticmethod
    def _step_batches(steps: list[PlanStep]) -> list[list[PlanStep]]:
        batches: list[list[PlanStep]] = []
        index = 0
        while index < len(steps):
            step = steps[index]
            if step.parallel_group is None:
                batches.append([step])
                index += 1
                continue

            group_name = step.parallel_group
            batch = [step]
            index += 1
            while index < len(steps) and steps[index].parallel_group == group_name:
                batch.append(steps[index])
                index += 1
            batches.append(batch)
        return batches

    def run(self, goal: WorkflowGoal) -> WorkflowResult:
        planner_context = PlannerContext(
            workflow_id=goal.workflow_id,
            goal=goal.goal,
            capabilities=goal.capabilities,
        )
        plan = self.planner.plan(goal.goal, planner_context)

        records = []
        status = WorkflowStatus.RUNNING

        for batch in self._step_batches(plan.steps):
            prior_results = list(records)
            if len(batch) == 1:
                batch_records = [
                    self._run_step(
                        step=batch[0],
                        workflow_id=goal.workflow_id,
                        prior_results=prior_results,
                    )
                ]
            else:
                with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                    futures = [
                        executor.submit(
                            self._run_step,
                            step=step,
                            workflow_id=goal.workflow_id,
                            prior_results=prior_results,
                        )
                        for step in batch
                    ]
                    batch_records = [future.result() for future in futures]

            records.extend(batch_records)

            if any(record.status == TaskStatus.FAILED for record in batch_records):
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
