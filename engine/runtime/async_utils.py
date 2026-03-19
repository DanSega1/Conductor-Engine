"""Helpers for bridging async providers into the sync Phase 1 runtime."""

from __future__ import annotations

import asyncio
from typing import Any


def run_coro(coro: Any) -> Any:
    """Run a coroutine from sync code when no event loop is active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    raise RuntimeError(
        "Cannot execute async memory provider from a running event loop via the sync capability. "
        "Use the MemoryProvider directly in async contexts."
    )
