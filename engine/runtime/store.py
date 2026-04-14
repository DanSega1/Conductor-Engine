"""Task store implementations for the minimal runtime."""

from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Protocol

from engine.interfaces.task import TaskRecord, TaskStatus

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX path
    msvcrt = None


def _normalize_status(status: TaskStatus | str | None) -> str | None:
    if isinstance(status, TaskStatus):
        return status.value
    return status


def _serialize_task(task: TaskRecord) -> str:
    return json.dumps(task.model_dump(mode="json"), sort_keys=True)


def _deserialize_task(payload: str | bytes | None) -> TaskRecord | None:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return TaskRecord.model_validate(json.loads(payload))


def _filter_records(
    records: list[TaskRecord],
    *,
    limit: int | None = None,
    offset: int = 0,
    status: TaskStatus | str | None = None,
) -> list[TaskRecord]:
    status_value = _normalize_status(status)
    if status_value is not None:
        records = [record for record in records if record.status == status_value]
    records = records[offset:]
    if limit is not None:
        records = records[:limit]
    return records


def _validate_identifier(value: str, *, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


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
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        """Return stored tasks, optionally filtered and paginated."""

    def health_check(self) -> list[str]:
        """Return structural issues for this store, if any."""


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
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        records = [self._tasks[task_id].model_copy(deep=True) for task_id in sorted(self._tasks)]
        return _filter_records(records, limit=limit, offset=offset, status=status)

    def health_check(self) -> list[str]:
        return []


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
        raw = self.path.read_text(encoding="utf-8")
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
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        payload = self._read()
        records = [TaskRecord.model_validate(record) for _, record in sorted(payload.items())]
        return _filter_records(records, limit=limit, offset=offset, status=status)

    def health_check(self) -> list[str]:
        issues: list[str] = []
        try:
            self._read()
        except json.JSONDecodeError as exc:
            issues.append(f"task store '{self.path}' is not valid JSON: {exc.msg}")
        except OSError as exc:
            issues.append(f"task store '{self.path}' is not readable: {exc}")
        return issues


class SQLiteTaskStore:
    """SQLite-backed task store for local durable execution."""

    def __init__(
        self,
        path: str | Path = ".conductor/tasks.sqlite3",
        *,
        table_name: str = "tasks",
    ) -> None:
        self.path = Path(path)
        self._table_name = _validate_identifier(table_name, label="SQLite table name")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    workflow_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {self._table_name}_status_created_idx
                ON {self._table_name} (status, created_at, task_id)
                """
            )

    def save(self, task: TaskRecord) -> TaskRecord:
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {self._table_name} (
                    task_id,
                    status,
                    workflow_id,
                    created_at,
                    updated_at,
                    payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    workflow_id = excluded.workflow_id,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    task.task_id,
                    task.status.value,
                    task.workflow_id,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    _serialize_task(task),
                ),
            )
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload FROM {self._table_name} WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _deserialize_task(row["payload"] if row else None)

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        status_value = _normalize_status(status)
        clauses: list[str] = []
        params: list[Any] = []
        if status_value is not None:
            clauses.append("status = ?")
            params.append(status_value)

        query = f"SELECT payload FROM {self._table_name}"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC, task_id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        if offset:
            if limit is None:
                query += " LIMIT -1"
            query += " OFFSET ?"
            params.append(offset)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [TaskRecord.model_validate(json.loads(row["payload"])) for row in rows]

    def health_check(self) -> list[str]:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
        except Exception as exc:
            return [f"SQLite health check failed for {self.path}: {exc}"]
        return []


class PostgresTaskStore:
    """Postgres-backed task store with lazy optional dependency loading."""

    def __init__(self, dsn: str, *, table_name: str = "conductor_tasks") -> None:
        self.dsn = dsn
        self._table_name = _validate_identifier(table_name, label="Postgres table name")
        try:
            self._psycopg = import_module("psycopg")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "PostgresTaskStore requires the 'psycopg' package. Install conductor-engine[postgres]."
            ) from exc
        self._initialize()

    def _connect(self) -> Any:
        return self._psycopg.connect(self.dsn)

    def _initialize(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        task_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        workflow_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        payload JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self._table_name}_status_created_idx
                    ON {self._table_name} (status, created_at, task_id)
                    """
                )
            connection.commit()

    def save(self, task: TaskRecord) -> TaskRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {self._table_name} (
                        task_id,
                        status,
                        workflow_id,
                        created_at,
                        updated_at,
                        payload
                    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT(task_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        workflow_id = EXCLUDED.workflow_id,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at,
                        payload = EXCLUDED.payload
                    """,
                    (
                        task.task_id,
                        task.status.value,
                        task.workflow_id,
                        task.created_at,
                        task.updated_at,
                        _serialize_task(task),
                    ),
                )
            connection.commit()
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT payload::text FROM {self._table_name} WHERE task_id = %s",
                    (task_id,),
                )
                row = cursor.fetchone()
        return _deserialize_task(row[0] if row else None)

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        status_value = _normalize_status(status)
        params: list[Any] = []
        query = f"SELECT payload::text FROM {self._table_name}"
        if status_value is not None:
            query += " WHERE status = %s"
            params.append(status_value)
        query += " ORDER BY created_at ASC, task_id ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        if offset:
            query += " OFFSET %s"
            params.append(offset)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [TaskRecord.model_validate(json.loads(row[0])) for row in rows]

    def health_check(self) -> list[str]:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
        except Exception as exc:
            return [f"Postgres health check failed: {exc}"]
        return []


class RedisTaskStore:
    """Redis-backed task store with a simple ID index."""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        namespace: str = "conductor:tasks",
        client: Any | None = None,
    ) -> None:
        self.url = url
        self.namespace = namespace
        if client is not None:
            self._client = client
            return
        try:
            redis = import_module("redis")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "RedisTaskStore requires the 'redis' package. Install conductor-engine[redis]."
            ) from exc
        self._client = redis.Redis.from_url(url, decode_responses=True)

    @property
    def _index_key(self) -> str:
        return f"{self.namespace}:ids"

    def _record_key(self, task_id: str) -> str:
        return f"{self.namespace}:record:{task_id}"

    def save(self, task: TaskRecord) -> TaskRecord:
        self._client.set(self._record_key(task.task_id), _serialize_task(task))
        self._client.sadd(self._index_key, task.task_id)
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        return _deserialize_task(self._client.get(self._record_key(task_id)))

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        task_ids = sorted(self._client.smembers(self._index_key))
        records = []
        for task_id in task_ids:
            normalized_id = task_id.decode("utf-8") if isinstance(task_id, bytes) else task_id
            record = self.get(normalized_id)
            if record is not None:
                records.append(record)
        return _filter_records(records, limit=limit, offset=offset, status=status)

    def health_check(self) -> list[str]:
        try:
            self._client.ping()
        except Exception as exc:
            return [f"Redis health check failed: {exc}"]
        return []
