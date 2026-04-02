"""Regression tests for the JSON-backed local task store."""

from __future__ import annotations

from pathlib import Path
import threading

from engine.interfaces.task import TaskRecord
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
