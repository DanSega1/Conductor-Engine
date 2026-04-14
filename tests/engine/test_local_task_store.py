"""Regression tests for the JSON-backed local task store."""

from __future__ import annotations

from pathlib import Path
import threading

from engine.interfaces.task import TaskRecord, TaskStatus
from engine.runtime.store import LocalTaskStore


def test_local_task_store_treats_empty_file_as_empty_store(tmp_path: Path) -> None:
    store_path = tmp_path / "tasks.json"
    store_path.write_text("")

    store = LocalTaskStore(store_path)

    assert store.list() == []


def test_local_task_store_preserves_all_records_under_concurrent_saves(tmp_path: Path) -> None:
    store_path = tmp_path / "tasks.json"
    barrier = threading.Barrier(8)

    def worker(worker_id: int) -> None:
        store = LocalTaskStore(store_path)
        barrier.wait()
        for iteration in range(10):
            store.save(TaskRecord(name=f"task-{worker_id}-{iteration}", capability="echo"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records = LocalTaskStore(store_path).list()
    names = {record.name for record in records}

    assert len(records) == 80
    assert len(names) == 80


def test_local_task_store_get_returns_independent_models(tmp_path: Path) -> None:
    store = LocalTaskStore(tmp_path / "tasks.json")
    original = TaskRecord(name="isolated", capability="echo", metadata={"count": 1})
    store.save(original)

    fetched = store.get(original.task_id)

    assert fetched is not None
    fetched.metadata["count"] = 99
    refetched = store.get(original.task_id)
    assert refetched is not None
    assert refetched.metadata["count"] == 1


def test_local_task_store_list_supports_offset_limit_and_status(tmp_path: Path) -> None:
    store = LocalTaskStore(tmp_path / "tasks.json")
    for index in range(3):
        store.save(
            TaskRecord(
                name=f"completed-{index}",
                capability="echo",
                status=TaskStatus.COMPLETED,
            )
        )
    for index in range(2):
        store.save(
            TaskRecord(
                name=f"failed-{index}",
                capability="echo",
                status=TaskStatus.FAILED,
            )
        )

    all_records = store.list()
    page = store.list(limit=2, offset=1)
    failed = store.list(status="failed")
    completed_page = store.list(status="completed", limit=2, offset=1)

    assert [record.task_id for record in page] == [record.task_id for record in all_records[1:3]]
    assert len(failed) == 2
    assert all(record.status == TaskStatus.FAILED for record in failed)
    assert len(completed_page) == 2
    assert all(record.status == TaskStatus.COMPLETED for record in completed_page)
