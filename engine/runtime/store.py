"""Task store implementations for the minimal runtime."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from typing import Protocol

from engine.interfaces.task import TaskRecord

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX path
    msvcrt = None


class TaskStore(Protocol):
    """Storage contract for task persistence."""

    def save(self, task: TaskRecord) -> TaskRecord:
        """Persist a task and return the stored record."""

    def get(self, task_id: str) -> TaskRecord | None:
        """Return a task by id if present."""

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
    ) -> list[TaskRecord]:
        """Return stored tasks, optionally filtered and paginated."""


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

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
    ) -> list[TaskRecord]:
        records = [
            self._tasks[task_id].model_copy(deep=True)
            for task_id in sorted(self._tasks)
        ]
        if status is not None:
            records = [r for r in records if r.status == status]
        records = records[offset:]
        if limit is not None:
            records = records[:limit]
        return records


class LocalTaskStore:
    """JSON-backed task store suitable for local CLI usage."""

    def __init__(self, path: str | Path = ".conductor/tasks.json") -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")

    @contextmanager
    def _locked(self) -> object:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as lock_file:
            self._acquire_lock(lock_file)
            try:
                yield
            finally:
                self._release_lock(lock_file)

    @staticmethod
    def _acquire_lock(lock_file: object) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return
        if msvcrt is not None:  # pragma: no cover - Windows fallback
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)

    @staticmethod
    def _release_lock(lock_file: object) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return
        if msvcrt is not None:  # pragma: no cover - Windows fallback
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    def _read_unlocked(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        raw = self.path.read_text()
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _write_unlocked(self, payload: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _read(self) -> dict[str, dict[str, object]]:
        with self._locked():
            return self._read_unlocked()

    def save(self, task: TaskRecord) -> TaskRecord:
        with self._locked():
            payload = self._read_unlocked()
            payload[task.task_id] = task.model_dump(mode="json")
            self._write_unlocked(payload)
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        payload = self._read()
        record = payload.get(task_id)
        return TaskRecord.model_validate(record) if record else None

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
    ) -> list[TaskRecord]:
        payload = self._read()
        records = [TaskRecord.model_validate(record) for _, record in sorted(payload.items())]
        if status is not None:
            records = [r for r in records if r.status == status]
        records = records[offset:]
        if limit is not None:
            records = records[:limit]
        return records
