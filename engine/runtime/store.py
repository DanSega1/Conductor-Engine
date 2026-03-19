"""Task store implementations for the minimal runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from engine.interfaces.task import TaskRecord


class TaskStore(Protocol):
    """Storage contract for task persistence."""

    def save(self, task: TaskRecord) -> TaskRecord:
        """Persist a task and return the stored record."""

    def get(self, task_id: str) -> TaskRecord | None:
        """Return a task by id if present."""

    def list(self) -> list[TaskRecord]:
        """Return all stored tasks."""


class MemoryTaskStore:
    """Simple in-memory task store used by tests or embedded runs."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def save(self, task: TaskRecord) -> TaskRecord:
        self._tasks[task.task_id] = task.model_copy(deep=True)
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        return task.model_copy(deep=True) if task else None

    def list(self) -> list[TaskRecord]:
        return [self._tasks[task_id].model_copy(deep=True) for task_id in sorted(self._tasks)]


class LocalTaskStore:
    """JSON-backed task store suitable for local CLI usage."""

    def __init__(self, path: str | Path = ".conductor/tasks.json") -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _write(self, payload: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def save(self, task: TaskRecord) -> TaskRecord:
        payload = self._read()
        payload[task.task_id] = task.model_dump(mode="json")
        self._write(payload)
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        payload = self._read()
        record = payload.get(task_id)
        return TaskRecord.model_validate(record) if record else None

    def list(self) -> list[TaskRecord]:
        payload = self._read()
        return [TaskRecord.model_validate(record) for _, record in sorted(payload.items())]
