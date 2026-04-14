"""Helpers for bridging async providers into the sync Phase 1 runtime."""

from __future__ import annotations

import asyncio
from queue import Queue
import threading
from typing import Any


def _run_coro_in_thread(coro: Any) -> Any:
    result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, asyncio.run(coro)))
        except BaseException as exc:  # pragma: no cover - passthrough path
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    success, value = result_queue.get()
    thread.join()
    if success:
        return value
    raise value


def run_coro(coro: Any) -> Any:
    """Run a coroutine from sync code in both sync and async hosts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    return _run_coro_in_thread(coro)
