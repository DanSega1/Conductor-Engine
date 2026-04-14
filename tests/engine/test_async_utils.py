"""Tests for the sync/async bridge helpers used by memory providers."""

from __future__ import annotations

import asyncio

from engine.runtime.async_utils import run_coro


async def _sample(value: str) -> str:
    return value


def test_run_coro_executes_when_no_loop_is_running() -> None:
    assert run_coro(_sample("ok")) == "ok"


def test_run_coro_executes_inside_running_loop() -> None:
    async def exercise() -> None:
        assert run_coro(_sample("ok-from-loop")) == "ok-from-loop"

    asyncio.run(exercise())
