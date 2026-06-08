"""Runtime scheduler adapters for external task triggers."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
import random
from time import sleep as default_sleep
from typing import Any, Protocol

from engine.interfaces.scheduler import ExternalTriggerAdapter, TriggerDispatch, TriggerSource
from engine.interfaces.task import TaskRecord, TaskSubmission


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


class WebhookTriggerAdapter:
    """External trigger adapter that turns webhook payloads into submissions.

    This adapter is transport-agnostic. Callers push incoming webhook payloads
    via `enqueue_payload()`, and the scheduler service consumes them through
    regular `poll()` cycles.
    """

    def __init__(
        self,
        *,
        name: str,
        mapper: Callable[[dict[str, Any]], TaskSubmission],
    ) -> None:
        self.name = name
        self._mapper = mapper
        self._pending_payloads: deque[tuple[datetime, dict[str, Any]]] = deque()

    def enqueue_payload(
        self,
        payload: dict[str, Any],
        *,
        received_at: datetime | None = None,
    ) -> None:
        self._pending_payloads.append((_normalize_now(received_at), dict(payload)))

    def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
        del now  # Webhook dispatch timing is based on reception time.

        dispatches: list[TriggerDispatch] = []
        while self._pending_payloads:
            scheduled_for, payload = self._pending_payloads.popleft()
            submission = self._mapper(payload)
            dispatches.append(
                TriggerDispatch(
                    source=TriggerSource.WEBHOOK,
                    trigger_name=self.name,
                    scheduled_for=scheduled_for,
                    submission=submission,
                )
            )
        return dispatches

    def health_check(self) -> list[str]:
        return []


class WebhookIngressService:
    """Minimal ingress boundary for HTTP-style webhook payload delivery.

    Transport layers (HTTP server, API gateway handler, etc.) should call
    `ingest()` after decoding request data.
    """

    def __init__(self, *, adapters: list[WebhookTriggerAdapter]) -> None:
        self._adapters_by_name = {adapter.name: adapter for adapter in adapters}

    def ingest(
        self,
        *,
        trigger_name: str,
        payload: dict[str, Any],
        received_at: datetime | None = None,
    ) -> None:
        adapter = self._adapters_by_name.get(trigger_name)
        if adapter is None:
            raise ValueError(f"Unknown webhook trigger {trigger_name!r}")

        adapter.enqueue_payload(payload, received_at=received_at)


class SubmissionSink(Protocol):
    """Minimal submit interface used by the scheduler service."""

    def submit(self, submission: TaskSubmission) -> TaskRecord:
        """Submit a task for supervisor-managed execution."""


class StopSignal(Protocol):
    """Stop flag abstraction compatible with threading or asyncio events."""

    def is_set(self) -> bool:
        """Return True when the loop should stop."""


class TriggerSchedulerService:
    """Polling service that forwards external trigger dispatches into submit()."""

    def __init__(
        self,
        *,
        adapters: list[ExternalTriggerAdapter],
        sink: SubmissionSink,
    ) -> None:
        self.adapters = adapters
        self.sink = sink
        self._runtime_issues: list[str] = []

    @staticmethod
    def _with_trigger_metadata(dispatch: TriggerDispatch) -> TaskSubmission:
        submission = dispatch.submission.model_copy(deep=True)
        submission.metadata = {
            **submission.metadata,
            "trigger": {
                "dispatch_id": dispatch.dispatch_id,
                "source": dispatch.source,
                "trigger_name": dispatch.trigger_name,
                "scheduled_for": dispatch.scheduled_for.isoformat(),
                "emitted_at": dispatch.emitted_at.isoformat(),
            },
        }
        return submission

    def run_once(self, *, now: datetime | None = None) -> list[TaskRecord]:
        self._runtime_issues = []
        submitted: list[TaskRecord] = []
        for adapter in self.adapters:
            try:
                dispatches = adapter.poll(now=now)
            except Exception as exc:
                self._runtime_issues.append(f"scheduler: adapter poll failed: {exc}")
                continue

            for dispatch in dispatches:
                submission = self._with_trigger_metadata(dispatch)
                submitted.append(self.sink.submit(submission))
        return submitted

    def health_check(self) -> list[str]:
        issues = list(self._runtime_issues)
        for adapter in self.adapters:
            try:
                issues.extend(adapter.health_check())
            except Exception as exc:
                issues.append(f"scheduler: adapter health check failed: {exc}")
        return issues


class TriggerSchedulerLoopRunner:
    """Lifecycle control loop for repeated TriggerSchedulerService polling."""

    def __init__(
        self,
        *,
        service: TriggerSchedulerService,
        base_poll_interval_seconds: float = 1.0,
        max_poll_interval_seconds: float = 30.0,
        backoff_multiplier: float = 2.0,
        jitter_ratio: float = 0.0,
        stop_signal: StopSignal | None = None,
        sleep_fn: Callable[[float], None] = default_sleep,
        random_fn: Callable[[], float] = random.random,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if base_poll_interval_seconds <= 0:
            raise ValueError("base_poll_interval_seconds must be > 0")
        if max_poll_interval_seconds < base_poll_interval_seconds:
            raise ValueError(
                "max_poll_interval_seconds must be >= base_poll_interval_seconds"
            )
        if backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if jitter_ratio < 0:
            raise ValueError("jitter_ratio must be >= 0")

        self.service = service
        self.base_poll_interval_seconds = base_poll_interval_seconds
        self.max_poll_interval_seconds = max_poll_interval_seconds
        self.backoff_multiplier = backoff_multiplier
        self.jitter_ratio = jitter_ratio
        self.stop_signal = stop_signal
        self.sleep_fn = sleep_fn
        self.random_fn = random_fn
        self.now_fn = now_fn

    def _should_stop(self) -> bool:
        if self.stop_signal is None:
            return False
        return self.stop_signal.is_set()

    def _compute_interval_seconds(self, *, consecutive_idle_cycles: int) -> float:
        if consecutive_idle_cycles <= 0:
            interval = self.base_poll_interval_seconds
        else:
            exponent = consecutive_idle_cycles - 1
            interval = self.base_poll_interval_seconds * (self.backoff_multiplier**exponent)
            interval = min(interval, self.max_poll_interval_seconds)

        if self.jitter_ratio > 0:
            interval += interval * self.jitter_ratio * self.random_fn()

        return interval

    def run(self, *, max_cycles: int | None = None) -> int:
        """Run polling cycles until max_cycles is reached or stop is signaled."""
        if max_cycles is not None and max_cycles < 0:
            raise ValueError("max_cycles must be >= 0")

        cycles_completed = 0
        consecutive_idle_cycles = 0

        while True:
            if self._should_stop():
                return cycles_completed
            if max_cycles is not None and cycles_completed >= max_cycles:
                return cycles_completed

            now = self.now_fn() if self.now_fn is not None else None
            submitted = self.service.run_once(now=now)
            cycles_completed += 1

            if submitted:
                consecutive_idle_cycles = 0
            else:
                consecutive_idle_cycles += 1

            if self._should_stop():
                return cycles_completed
            if max_cycles is not None and cycles_completed >= max_cycles:
                return cycles_completed

            sleep_seconds = self._compute_interval_seconds(
                consecutive_idle_cycles=consecutive_idle_cycles
            )
            self.sleep_fn(sleep_seconds)
