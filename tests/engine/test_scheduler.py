"""Tests for scheduler contracts and cron trigger adapter."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine.interfaces.scheduler import TriggerSource
from engine.interfaces.task import TaskSubmission
from engine.runtime.scheduler import CronSchedule, CronTriggerAdapter


def _dt(*, year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_cron_schedule_matches_exact_expression() -> None:
    schedule = CronSchedule("15 10 * * *")

    assert schedule.matches(_dt(year=2026, month=6, day=7, hour=10, minute=15))
    assert not schedule.matches(_dt(year=2026, month=6, day=7, hour=10, minute=14))


def test_cron_schedule_supports_step_tokens() -> None:
    schedule = CronSchedule("*/5 * * * *")

    assert schedule.matches(_dt(year=2026, month=6, day=7, hour=10, minute=0))
    assert schedule.matches(_dt(year=2026, month=6, day=7, hour=10, minute=55))
    assert not schedule.matches(_dt(year=2026, month=6, day=7, hour=10, minute=57))


def test_cron_schedule_supports_comma_separated_values() -> None:
    schedule = CronSchedule("0 8,12,16 * * *")

    assert schedule.matches(_dt(year=2026, month=6, day=7, hour=12, minute=0))
    assert not schedule.matches(_dt(year=2026, month=6, day=7, hour=11, minute=0))


@pytest.mark.parametrize(
    "expression",
    [
        "* * * *",  # too few fields
        "* * * * * *",  # too many fields
        "foo * * * *",  # invalid token
        "*/0 * * * *",  # invalid step
        "61 * * * *",  # out of range
    ],
)
def test_cron_schedule_rejects_invalid_expressions(expression: str) -> None:
    with pytest.raises(ValueError):
        CronSchedule(expression)


def test_cron_trigger_adapter_emits_single_dispatch_for_matching_slot() -> None:
    submission = TaskSubmission(name="cron-echo", capability="echo", input={"message": "tick"})
    adapter = CronTriggerAdapter(name="every-five", schedule="*/5 * * * *", submission=submission)

    now = _dt(year=2026, month=6, day=7, hour=12, minute=10)
    first = adapter.poll(now=now)
    second = adapter.poll(now=now)

    assert len(first) == 1
    assert second == []
    assert first[0].source == TriggerSource.CRON
    assert first[0].trigger_name == "every-five"
    assert first[0].submission.name == "cron-echo"


def test_cron_trigger_adapter_emits_again_on_new_matching_slot() -> None:
    submission = TaskSubmission(name="cron-echo", capability="echo", input={"message": "tick"})
    adapter = CronTriggerAdapter(name="every-five", schedule="*/5 * * * *", submission=submission)

    first = adapter.poll(now=_dt(year=2026, month=6, day=7, hour=12, minute=10))
    next_slot = adapter.poll(now=_dt(year=2026, month=6, day=7, hour=12, minute=15))

    assert len(first) == 1
    assert len(next_slot) == 1


def test_cron_trigger_adapter_does_not_emit_when_not_matching() -> None:
    submission = TaskSubmission(name="cron-echo", capability="echo", input={"message": "tick"})
    adapter = CronTriggerAdapter(name="hourly", schedule="0 * * * *", submission=submission)

    dispatches = adapter.poll(now=_dt(year=2026, month=6, day=7, hour=12, minute=1))

    assert dispatches == []
