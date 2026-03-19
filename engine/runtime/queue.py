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
