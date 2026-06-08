"""Tests for scheduler contracts and cron trigger adapter."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine.interfaces.scheduler import TriggerDispatch, TriggerSource
from engine.interfaces.task import TaskRecord, TaskSubmission
from engine.runtime.scheduler import (
    CronSchedule,
    CronTriggerAdapter,
    TriggerSchedulerLoopRunner,
    TriggerSchedulerService,
    WebhookIngressService,
    WebhookTriggerAdapter,
)


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


def test_trigger_scheduler_service_submits_dispatched_tasks_with_trigger_metadata() -> None:
    class OneShotAdapter:
        def __init__(self) -> None:
            self._emitted = False

        def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
            if self._emitted:
                return []
            self._emitted = True
            return [
                TriggerDispatch(
                    source=TriggerSource.CRON,
                    trigger_name="hourly-sync",
                    scheduled_for=_dt(year=2026, month=6, day=7, hour=12, minute=0),
                    submission=TaskSubmission(
                        name="sync",
                        capability="echo",
                        input={"message": "hello"},
                    ),
                )
            ]

        def health_check(self) -> list[str]:
            return []

    class CapturingSink:
        def __init__(self) -> None:
            self.submissions: list[TaskSubmission] = []

        def submit(self, submission: TaskSubmission) -> TaskRecord:
            self.submissions.append(submission)
            return TaskRecord(
                name=submission.name,
                capability=submission.capability,
                input=submission.input,
                metadata=submission.metadata,
            )

    adapter = OneShotAdapter()
    sink = CapturingSink()
    service = TriggerSchedulerService(adapters=[adapter], sink=sink)

    submitted_records = service.run_once(now=_dt(year=2026, month=6, day=7, hour=12, minute=0))

    assert len(submitted_records) == 1
    assert len(sink.submissions) == 1
    assert sink.submissions[0].metadata["trigger"]["source"] == TriggerSource.CRON.value
    assert sink.submissions[0].metadata["trigger"]["trigger_name"] == "hourly-sync"
    assert service.health_check() == []


def test_trigger_scheduler_service_collects_runtime_and_health_issues() -> None:
    class FailingAdapter:
        def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
            raise RuntimeError("poll blew up")

        def health_check(self) -> list[str]:
            return ["adapter unhealthy"]

    class NoopSink:
        def submit(self, submission: TaskSubmission) -> TaskRecord:
            return TaskRecord(
                name=submission.name,
                capability=submission.capability,
                input=submission.input,
                metadata=submission.metadata,
            )

    service = TriggerSchedulerService(adapters=[FailingAdapter()], sink=NoopSink())

    submitted_records = service.run_once(now=_dt(year=2026, month=6, day=7, hour=12, minute=0))
    issues = service.health_check()

    assert submitted_records == []
    assert any("adapter poll failed" in issue for issue in issues)
    assert any("adapter unhealthy" in issue for issue in issues)


def test_webhook_trigger_adapter_emits_dispatched_submissions_from_queue() -> None:
    adapter = WebhookTriggerAdapter(
        name="webhook-github",
        mapper=lambda payload: TaskSubmission(
            name=f"webhook:{payload['event']}",
            capability="echo",
            input={"payload": payload},
        ),
    )

    received_at = _dt(year=2026, month=6, day=7, hour=13, minute=5)
    adapter.enqueue_payload({"event": "push", "repo": "Conductor-Engine"}, received_at=received_at)

    dispatches = adapter.poll()

    assert len(dispatches) == 1
    assert dispatches[0].source == TriggerSource.WEBHOOK
    assert dispatches[0].trigger_name == "webhook-github"
    assert dispatches[0].scheduled_for == received_at
    assert dispatches[0].submission.name == "webhook:push"
    assert dispatches[0].submission.input["payload"]["repo"] == "Conductor-Engine"


def test_webhook_trigger_adapter_drains_queue_once_per_poll_cycle() -> None:
    adapter = WebhookTriggerAdapter(
        name="webhook-github",
        mapper=lambda payload: TaskSubmission(
            name=f"webhook:{payload['event']}",
            capability="echo",
        ),
    )
    adapter.enqueue_payload({"event": "push"})

    first = adapter.poll()
    second = adapter.poll()

    assert len(first) == 1
    assert second == []


def test_webhook_ingress_service_enqueues_payload_to_named_adapter() -> None:
    adapter = WebhookTriggerAdapter(
        name="webhook-github",
        mapper=lambda payload: TaskSubmission(
            name=f"webhook:{payload['event']}",
            capability="echo",
            input={"payload": payload},
        ),
    )
    ingress = WebhookIngressService(adapters=[adapter])

    ingress.ingest(
        trigger_name="webhook-github",
        payload={"event": "push", "repo": "Conductor-Engine"},
        received_at=_dt(year=2026, month=6, day=7, hour=14, minute=0),
    )
    dispatches = adapter.poll()

    assert len(dispatches) == 1
    assert dispatches[0].source == TriggerSource.WEBHOOK
    assert dispatches[0].submission.name == "webhook:push"


def test_webhook_ingress_service_rejects_unknown_trigger() -> None:
    adapter = WebhookTriggerAdapter(
        name="webhook-github",
        mapper=lambda payload: TaskSubmission(name="ok", capability="echo", input=payload),
    )
    ingress = WebhookIngressService(adapters=[adapter])

    with pytest.raises(ValueError, match="Unknown webhook trigger"):
        ingress.ingest(trigger_name="missing", payload={"event": "push"})


def test_webhook_ingress_to_scheduler_service_end_to_end() -> None:
    adapter = WebhookTriggerAdapter(
        name="webhook-github",
        mapper=lambda payload: TaskSubmission(
            name=f"webhook:{payload['event']}",
            capability="echo",
            input={"payload": payload},
        ),
    )
    ingress = WebhookIngressService(adapters=[adapter])

    class CapturingSink:
        def __init__(self) -> None:
            self.submissions: list[TaskSubmission] = []

        def submit(self, submission: TaskSubmission) -> TaskRecord:
            self.submissions.append(submission)
            return TaskRecord(
                name=submission.name,
                capability=submission.capability,
                input=submission.input,
                metadata=submission.metadata,
            )

    sink = CapturingSink()
    service = TriggerSchedulerService(adapters=[adapter], sink=sink)

    ingress.ingest(
        trigger_name="webhook-github",
        payload={"event": "push", "repo": "Conductor-Engine"},
        received_at=_dt(year=2026, month=6, day=7, hour=14, minute=10),
    )
    submitted = service.run_once(now=_dt(year=2026, month=6, day=7, hour=14, minute=11))

    assert len(submitted) == 1
    assert len(sink.submissions) == 1
    assert sink.submissions[0].name == "webhook:push"
    assert sink.submissions[0].metadata["trigger"]["source"] == TriggerSource.WEBHOOK.value
    assert sink.submissions[0].input["payload"]["repo"] == "Conductor-Engine"


def _record(name: str) -> TaskRecord:
    return TaskRecord(name=name, capability="echo")


class _StopAfterCycles:
    def __init__(self, *, limit: int) -> None:
        self.limit = limit
        self.cycles_seen = 0

    def mark_cycle(self) -> None:
        self.cycles_seen += 1

    def is_set(self) -> bool:
        return self.cycles_seen >= self.limit


def test_scheduler_loop_runner_respects_max_cycles() -> None:
    class EmptyAdapter:
        def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
            return []

        def health_check(self) -> list[str]:
            return []

    class CapturingSink:
        def submit(self, submission: TaskSubmission) -> TaskRecord:
            return _record(submission.name)

    service = TriggerSchedulerService(adapters=[EmptyAdapter()], sink=CapturingSink())
    sleeps: list[float] = []

    runner = TriggerSchedulerLoopRunner(
        service=service,
        base_poll_interval_seconds=1.0,
        max_poll_interval_seconds=8.0,
        sleep_fn=sleeps.append,
    )

    cycles = runner.run(max_cycles=3)

    assert cycles == 3
    assert sleeps == [1.0, 2.0]


def test_scheduler_loop_runner_applies_backoff_and_resets_after_work() -> None:
    class ScriptedAdapter:
        def __init__(self) -> None:
            self._polls = 0

        def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
            self._polls += 1
            if self._polls == 3:
                return [
                    TriggerDispatch(
                        source=TriggerSource.CRON,
                        trigger_name="scripted",
                        scheduled_for=_dt(year=2026, month=6, day=7, hour=12, minute=0),
                        submission=TaskSubmission(name="tick", capability="echo"),
                    )
                ]
            return []

        def health_check(self) -> list[str]:
            return []

    class CapturingSink:
        def submit(self, submission: TaskSubmission) -> TaskRecord:
            return _record(submission.name)

    service = TriggerSchedulerService(adapters=[ScriptedAdapter()], sink=CapturingSink())
    sleeps: list[float] = []

    runner = TriggerSchedulerLoopRunner(
        service=service,
        base_poll_interval_seconds=1.0,
        max_poll_interval_seconds=8.0,
        sleep_fn=sleeps.append,
    )

    cycles = runner.run(max_cycles=5)

    assert cycles == 5
    assert sleeps == [1.0, 2.0, 1.0, 1.0]


def test_scheduler_loop_runner_stops_gracefully_from_stop_signal() -> None:
    stop = _StopAfterCycles(limit=2)

    class EmptyAdapter:
        def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
            stop.mark_cycle()
            return []

        def health_check(self) -> list[str]:
            return []

    class CapturingSink:
        def submit(self, submission: TaskSubmission) -> TaskRecord:
            return _record(submission.name)

    service = TriggerSchedulerService(adapters=[EmptyAdapter()], sink=CapturingSink())
    sleeps: list[float] = []

    runner = TriggerSchedulerLoopRunner(
        service=service,
        base_poll_interval_seconds=1.0,
        max_poll_interval_seconds=8.0,
        stop_signal=stop,
        sleep_fn=sleeps.append,
    )

    cycles = runner.run()

    assert cycles == 2
    assert sleeps == [1.0]


def test_scheduler_loop_runner_uses_deterministic_jitter_hook() -> None:
    class EmptyAdapter:
        def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
            return []

        def health_check(self) -> list[str]:
            return []

    class CapturingSink:
        def submit(self, submission: TaskSubmission) -> TaskRecord:
            return _record(submission.name)

    service = TriggerSchedulerService(adapters=[EmptyAdapter()], sink=CapturingSink())
    sleeps: list[float] = []

    jitter_values = iter([0.5, 0.25])
    runner = TriggerSchedulerLoopRunner(
        service=service,
        base_poll_interval_seconds=2.0,
        max_poll_interval_seconds=8.0,
        jitter_ratio=0.1,
        random_fn=lambda: next(jitter_values),
        sleep_fn=sleeps.append,
    )

    cycles = runner.run(max_cycles=3)

    assert cycles == 3
    assert sleeps == [2.1, 4.1]
