"""Runtime scheduler adapters for external task triggers."""

from __future__ import annotations

from datetime import UTC, datetime

from engine.interfaces.scheduler import TriggerDispatch, TriggerSource
from engine.interfaces.task import TaskSubmission


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(tz=UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _field_matches(
    value: int,
    field_spec: str,
    *,
    minimum: int,
    maximum: int,
    allow_weekday_7: bool = False,
) -> bool:
    for token in (part.strip() for part in field_spec.split(",")):
        if not token:
            continue

        if token == "*":
            return True

        if token.startswith("*/"):
            step_str = token[2:]
            if not step_str.isdigit():
                raise ValueError(f"Invalid step value {token!r}")
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be > 0 in {token!r}")
            return value % step == 0

        if token.isdigit():
            candidate = int(token)
            if allow_weekday_7 and candidate == 7:
                candidate = 0
            if candidate < minimum or candidate > maximum:
                raise ValueError(f"Value {candidate} out of range for field {field_spec!r}")
            if value == candidate:
                return True
            continue

        raise ValueError(f"Unsupported cron token {token!r}")

    return False


class CronSchedule:
    """Minimal cron expression matcher supporting 5-field UTC schedules.

    Supported tokens per field:
    - "*"
    - "*/N"
    - comma-separated literal values, e.g. "1,15,30"
    """

    def __init__(self, expression: str) -> None:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(
                "Cron expression must have 5 fields: minute hour day month weekday"
            )

        self.expression = expression
        self.minute, self.hour, self.day, self.month, self.weekday = parts

        # Validate field tokens early so configuration errors fail fast.
        self.matches(datetime(2026, 1, 1, tzinfo=UTC))

    def matches(self, when: datetime) -> bool:
        check = _normalize_now(when)
        weekday = (check.weekday() + 1) % 7  # Monday=0..Sunday=6 -> Sunday=0
        return (
            _field_matches(check.minute, self.minute, minimum=0, maximum=59)
            and _field_matches(check.hour, self.hour, minimum=0, maximum=23)
            and _field_matches(check.day, self.day, minimum=1, maximum=31)
            and _field_matches(check.month, self.month, minimum=1, maximum=12)
            and _field_matches(
                weekday,
                self.weekday,
                minimum=0,
                maximum=6,
                allow_weekday_7=True,
            )
        )


class CronTriggerAdapter:
    """External trigger adapter that emits task submissions from a cron schedule."""

    def __init__(
        self,
        *,
        name: str,
        schedule: str,
        submission: TaskSubmission,
    ) -> None:
        self.name = name
        self.schedule = CronSchedule(schedule)
        self.submission = submission
        self._last_emitted_slot: tuple[int, int, int, int, int] | None = None

    @staticmethod
    def _slot_key(when: datetime) -> tuple[int, int, int, int, int]:
        normalized = _normalize_now(when)
        return (
            normalized.year,
            normalized.month,
            normalized.day,
            normalized.hour,
            normalized.minute,
        )

    def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
        current = _normalize_now(now)
        if not self.schedule.matches(current):
            return []

        slot = self._slot_key(current)
        if slot == self._last_emitted_slot:
            return []

        self._last_emitted_slot = slot
        return [
            TriggerDispatch(
                source=TriggerSource.CRON,
                trigger_name=self.name,
                scheduled_for=current,
                submission=self.submission.model_copy(deep=True),
            )
        ]

    def health_check(self) -> list[str]:
        return []
