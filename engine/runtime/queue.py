"""Queue primitives for the minimal single-process runtime."""

from __future__ import annotations

from collections import deque


class InMemoryTaskQueue:
    """Small FIFO queue used by the local supervisor."""

    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def enqueue(self, task_id: str) -> None:
        self._queue.append(task_id)

    def dequeue(self) -> str | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def list(self) -> list[str]:
        return list(self._queue)

    @property
    def size(self) -> int:
        return len(self._queue)

    def health_check(self) -> list[str]:
        issues: list[str] = []
        return issues


class BoundedTaskQueue:
    """FIFO queue with a maximum capacity.

    Raises ``QueueFull`` when the queue is at capacity and a caller
    attempts to enqueue another task.  This provides backpressure to
    API callers and prevents resource exhaustion under load.
    """

    def __init__(self, max_size: int = 512) -> None:
        self._queue: deque[str] = deque()
        self._max_size = max_size

    def enqueue(self, task_id: str) -> None:
        if len(self._queue) >= self._max_size:
            raise QueueFull(
                f"Queue is full ({self._max_size} tasks). "
                "Wait for tasks to complete before submitting more."
            )
        self._queue.append(task_id)

    def dequeue(self) -> str | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def list(self) -> list[str]:
        return list(self._queue)

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def available(self) -> int:
        """Number of slots remaining before the queue is full."""
        return self._max_size - len(self._queue)

    @property
    def utilization(self) -> float:
        """Fraction of queue capacity in use (0.0 to 1.0)."""
        if self._max_size == 0:
            return 1.0
        return len(self._queue) / self._max_size

    def health_check(self) -> list[str]:
        issues: list[str] = []
        if self.utilization > 0.9:
            issues.append(f"queue: {self.utilization:.0%} full ({len(self._queue)}/{self._max_size})")
        return issues


class QueueFull(Exception):
    """Raised when the task queue has reached its maximum capacity."""
