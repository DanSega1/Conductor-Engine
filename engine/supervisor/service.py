"""Minimal supervisor: Task -> Capability -> Result."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from engine.guardrails.validation import validate_task_submission
from engine.interfaces.capability import CapabilityContext
from engine.interfaces.task import TaskRecord, TaskResult, TaskStatus, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.queue import InMemoryTaskQueue
from engine.runtime.store import TaskStore


def _now() -> datetime:
    return datetime.now(tz=UTC)


class TaskSupervisor:
    """Single-process task supervisor for Phase 1 engine workflows."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        store: TaskStore,
        queue: InMemoryTaskQueue | None = None,
        workdir: str | Path | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.queue = queue or InMemoryTaskQueue()
        self.workdir = str(Path(workdir or Path.cwd()).resolve())

    def submit(self, submission: TaskSubmission) -> TaskRecord:
        validate_task_submission(submission, self.registry)
        task = TaskRecord(
            name=submission.name,
            capability=submission.capability,
            input=submission.input,
            metadata=submission.metadata,
        )
        self.store.save(task)
        self.queue.enqueue(task.task_id)
        return task

    def run_submission(self, submission: TaskSubmission) -> TaskRecord:
        self.submit(submission)
        return self.run_next()

    def run_next(self) -> TaskRecord:
        task_id = self.queue.dequeue()
        if task_id is None:
            raise ValueError("No queued tasks are available")
        return self.run_task(task_id)

    def run_task(self, task_id: str) -> TaskRecord:
        task = self.store.get(task_id)
        if task is None:
            raise ValueError(f"Task '{task_id}' was not found")

        submission = TaskSubmission(
            name=task.name,
            capability=task.capability,
            input=task.input,
            metadata=task.metadata,
        )
        capability = validate_task_submission(submission, self.registry)

        started_at = _now()
        task.status = TaskStatus.RUNNING
        task.updated_at = started_at
        self.store.save(task)

        try:
            payload = capability.validate_input(task.input)
            result = capability.execute(
                payload,
                CapabilityContext(
                    task_id=task.task_id,
                    task_name=task.name,
                    workdir=self.workdir,
                ),
            )
            task.result = TaskResult(
                success=True,
                output=result.output,
                metadata=result.metadata,
                started_at=started_at,
                completed_at=_now(),
            )
            task.status = TaskStatus.COMPLETED
        except Exception as exc:
            task.result = TaskResult(
                success=False,
                error=str(exc),
                started_at=started_at,
                completed_at=_now(),
            )
            task.status = TaskStatus.FAILED

        task.updated_at = _now()
        self.store.save(task)
        return task

    def list_tasks(self) -> list[TaskRecord]:
        return self.store.list()
