"""Tests for the bounded task queue."""

from __future__ import annotations

import pytest

from engine.runtime.queue import BoundedTaskQueue, QueueFull


def test_bounded_queue_default_max_size() -> None:
    q = BoundedTaskQueue()
    assert q.max_size == 512
    assert q.size == 0
    assert q.available == 512
    assert q.utilization == 0.0


def test_bounded_queue_custom_max_size() -> None:
    q = BoundedTaskQueue(max_size=10)
    assert q.max_size == 10


def test_enqueue_dequeue_fifo() -> None:
    q = BoundedTaskQueue(max_size=10)
    q.enqueue("a")
    q.enqueue("b")
    assert q.dequeue() == "a"
    assert q.dequeue() == "b"
    assert q.dequeue() is None


def test_list_returns_snapshot() -> None:
    q = BoundedTaskQueue(max_size=10)
    q.enqueue("a")
    q.enqueue("b")
    assert q.list() == ["a", "b"]
    q.dequeue()
    assert q.list() == ["b"]


def test_available_decreases_on_enqueue() -> None:
    q = BoundedTaskQueue(max_size=5)
    assert q.available == 5
    q.enqueue("a")
    assert q.available == 4
    q.enqueue("b")
    assert q.available == 3
    q.dequeue()
    assert q.available == 4


def test_utilization_tracks_fill_level() -> None:
    q = BoundedTaskQueue(max_size=4)
    assert q.utilization == 0.0
    q.enqueue("a")
    assert q.utilization == 0.25
    q.enqueue("b")
    assert q.utilization == 0.5
    q.enqueue("c")
    assert q.utilization == 0.75
    q.enqueue("d")
    assert q.utilization == 1.0


def test_queue_raises_on_overflow() -> None:
    q = BoundedTaskQueue(max_size=2)
    q.enqueue("a")
    q.enqueue("b")
    with pytest.raises(QueueFull, match="Queue is full"):
        q.enqueue("c")


def test_queue_full_is_exception() -> None:
    assert issubclass(QueueFull, Exception)


def test_health_check_empty() -> None:
    q = BoundedTaskQueue(max_size=100)
    assert q.health_check() == []


def test_health_check_near_capacity() -> None:
    q = BoundedTaskQueue(max_size=10)
    for i in range(9):
        q.enqueue(f"t{i}")
    # 90% — still OK
    assert q.health_check() == []

    q.enqueue("t10")
    # 100% — warning
    issues = q.health_check()
    assert len(issues) >= 1
    assert "queue" in issues[0]
    assert "100%" in issues[0]


def test_multiple_queues_are_independent() -> None:
    q1 = BoundedTaskQueue(max_size=3)
    q2 = BoundedTaskQueue(max_size=3)
    q1.enqueue("a")
    q2.enqueue("b")
    assert q1.dequeue() == "a"
    assert q2.dequeue() == "b"


def test_dequeue_empty() -> None:
    q = BoundedTaskQueue(max_size=5)
    assert q.dequeue() is None
    assert q.size == 0
