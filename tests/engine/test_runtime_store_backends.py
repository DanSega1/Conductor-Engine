"""Focused tests for Phase 3 task store backends."""

from __future__ import annotations

from typing import Any

import pytest

from engine.interfaces.task import TaskRecord, TaskStatus
from engine.runtime.store import PostgresTaskStore, RedisTaskStore, SQLiteTaskStore


def test_sqlite_task_store_round_trips_and_filters(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "tasks.sqlite3")
    completed = TaskRecord(
        name="completed-task",
        capability="echo",
        status=TaskStatus.COMPLETED,
        workflow_id="wf-1",
    )
    failed = TaskRecord(name="failed-task", capability="echo", status=TaskStatus.FAILED)

    store.save(completed)
    store.save(failed)

    stored = store.get(completed.task_id)

    assert stored is not None
    assert stored.workflow_id == "wf-1"
    assert [record.status for record in store.list(status=TaskStatus.COMPLETED)] == [
        TaskStatus.COMPLETED
    ]
    assert len(store.list(limit=1, offset=1)) == 1
    assert store.health_check() == []


def test_postgres_task_store_requires_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("engine.runtime.store.import_module", fake_import)

    with pytest.raises(RuntimeError, match="psycopg"):
        PostgresTaskStore("postgresql://localhost/conductor")


class FakeRedisClient:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._sets: dict[str, set[str]] = {}

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def sadd(self, key: str, value: str) -> None:
        self._sets.setdefault(key, set()).add(value)

    def smembers(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    def ping(self) -> bool:
        return True


def test_redis_task_store_round_trips_with_injected_client() -> None:
    store = RedisTaskStore(client=FakeRedisClient())
    completed = TaskRecord(name="completed-task", capability="echo", status=TaskStatus.COMPLETED)
    pending = TaskRecord(name="pending-task", capability="echo", status=TaskStatus.PENDING)

    store.save(completed)
    store.save(pending)

    assert store.get(completed.task_id) == completed
    assert [record.status for record in store.list(status=TaskStatus.COMPLETED)] == [
        TaskStatus.COMPLETED
    ]
    assert store.health_check() == []


def test_redis_task_store_requires_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("engine.runtime.store.import_module", fake_import)

    with pytest.raises(RuntimeError, match="redis"):
        RedisTaskStore()
