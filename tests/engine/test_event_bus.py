"""Tests for the EventBus interface, implementations, and supervisor integration."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from engine.capabilities.echo import EchoCapability
from engine.interfaces.capability import CapabilityContext, CapabilityDescriptor, CapabilityResult
from engine.interfaces.event import EventBus, EventType, TaskEvent
from engine.interfaces.task import RiskLevel, TaskStatus, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.bus import LoggingEventBus, NullEventBus
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor

# ---------------------------------------------------------------------------
# TaskEvent model
# ---------------------------------------------------------------------------


def test_task_event_required_fields() -> None:
    event = TaskEvent(
        event_type=EventType.TASK_STARTED,
        task_id="abc",
        task_name="my-task",
        capability="echo",
        status=TaskStatus.RUNNING,
        attempt=1,
    )
    assert event.event_type == EventType.TASK_STARTED
    assert event.task_id == "abc"
    assert event.attempt == 1
    assert event.workflow_id is None
    assert event.error is None
    assert event.metadata == {}


def test_task_event_with_workflow_id() -> None:
    event = TaskEvent(
        event_type=EventType.TASK_COMPLETED,
        task_id="t1",
        task_name="n",
        capability="echo",
        status=TaskStatus.COMPLETED,
        attempt=1,
        workflow_id="wf-99",
    )
    assert event.workflow_id == "wf-99"


def test_task_event_with_error() -> None:
    event = TaskEvent(
        event_type=EventType.TASK_FAILED,
        task_id="t1",
        task_name="n",
        capability="echo",
        status=TaskStatus.FAILED,
        attempt=2,
        error="boom",
    )
    assert event.error == "boom"


# ---------------------------------------------------------------------------
# EventType enum
# ---------------------------------------------------------------------------


def test_event_type_values() -> None:
    assert EventType.TASK_STARTED == "task_started"
    assert EventType.TASK_COMPLETED == "task_completed"
    assert EventType.TASK_FAILED == "task_failed"


# ---------------------------------------------------------------------------
# NullEventBus
# ---------------------------------------------------------------------------


def test_null_event_bus_emit_does_nothing() -> None:
    bus = NullEventBus()
    event = TaskEvent(
        event_type=EventType.TASK_STARTED,
        task_id="x",
        task_name="x",
        capability="echo",
        status=TaskStatus.RUNNING,
        attempt=1,
    )
    bus.emit(event)  # must not raise


def test_null_event_bus_satisfies_protocol() -> None:
    bus: EventBus = NullEventBus()
    assert hasattr(bus, "emit")


# ---------------------------------------------------------------------------
# LoggingEventBus
# ---------------------------------------------------------------------------


def test_logging_event_bus_emits_info_for_started(caplog: pytest.LogCaptureFixture) -> None:
    bus = LoggingEventBus()
    event = TaskEvent(
        event_type=EventType.TASK_STARTED,
        task_id="t1",
        task_name="test-task",
        capability="echo",
        status=TaskStatus.RUNNING,
        attempt=1,
    )
    with caplog.at_level(logging.INFO, logger="engine.runtime.bus"):
        bus.emit(event)
    assert any("task_started" in r.message for r in caplog.records)


def test_logging_event_bus_emits_warning_for_failed(caplog: pytest.LogCaptureFixture) -> None:
    bus = LoggingEventBus()
    event = TaskEvent(
        event_type=EventType.TASK_FAILED,
        task_id="t1",
        task_name="test-task",
        capability="echo",
        status=TaskStatus.FAILED,
        attempt=1,
        error="something broke",
    )
    with caplog.at_level(logging.WARNING, logger="engine.runtime.bus"):
        bus.emit(event)
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert any("something broke" in r.message for r in caplog.records)


def test_logging_event_bus_accepts_custom_logger() -> None:
    custom = logging.getLogger("custom.test")
    bus = LoggingEventBus(log=custom)
    assert bus._log is custom


# ---------------------------------------------------------------------------
# Supervisor integration — event_bus wiring
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class BombCapability:
    """Always raises — used to force TASK_FAILED in integration tests."""

    descriptor = CapabilityDescriptor(
        name="bomb",
        description="always fails",
        risk_level=RiskLevel.LOW,
    )

    def validate_input(self, raw: dict) -> dict:  # type: ignore[override]
        return raw

    def execute(self, payload: dict, context: CapabilityContext) -> CapabilityResult:  # type: ignore[override]
        raise RuntimeError("bomb exploded")


def _make_supervisor(bus: EventBus | None = None) -> TaskSupervisor:
    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    registry.register(BombCapability())
    store = MemoryTaskStore()
    return TaskSupervisor(registry=registry, store=store, event_bus=bus)


def test_supervisor_defaults_to_null_bus() -> None:
    sv = _make_supervisor()
    assert isinstance(sv._bus, NullEventBus)


def test_supervisor_uses_provided_bus() -> None:
    bus = NullEventBus()
    sv = _make_supervisor(bus=bus)
    assert sv._bus is bus


def test_supervisor_emits_started_and_completed_on_success() -> None:
    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    sv = _make_supervisor(bus=CapturingBus())
    sv.run_submission(TaskSubmission(name="t", capability="echo", input={"message": "hi"}))

    event_types = [e.event_type for e in captured]
    assert EventType.TASK_STARTED in event_types
    assert EventType.TASK_COMPLETED in event_types
    assert EventType.TASK_FAILED not in event_types


def test_supervisor_emits_started_and_failed_on_failure() -> None:
    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    sv = _make_supervisor(bus=CapturingBus())
    sv.run_submission(TaskSubmission(name="t", capability="bomb", input={}))

    event_types = [e.event_type for e in captured]
    assert EventType.TASK_STARTED in event_types
    assert EventType.TASK_FAILED in event_types
    assert EventType.TASK_COMPLETED not in event_types


def test_supervisor_started_event_carries_task_id() -> None:
    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    sv = _make_supervisor(bus=CapturingBus())
    record = sv.run_submission(
        TaskSubmission(name="t", capability="echo", input={"message": "hi"})
    )

    started = next(e for e in captured if e.event_type == EventType.TASK_STARTED)
    assert started.task_id == record.task_id
    assert started.task_name == record.name


def test_supervisor_completed_event_has_correct_attempt() -> None:
    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    sv = _make_supervisor(bus=CapturingBus())
    sv.run_submission(TaskSubmission(name="t", capability="echo", input={"message": "hi"}))

    completed = next(e for e in captured if e.event_type == EventType.TASK_COMPLETED)
    assert completed.attempt == 1


def test_supervisor_failed_event_carries_error_message() -> None:
    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    sv = _make_supervisor(bus=CapturingBus())
    sv.run_submission(TaskSubmission(name="t", capability="bomb", input={}))

    failed = next(e for e in captured if e.event_type == EventType.TASK_FAILED)
    assert failed.error is not None
    assert len(failed.error) > 0


def test_supervisor_mock_bus_called_twice_on_success() -> None:
    mock_bus = MagicMock()
    sv = _make_supervisor(bus=mock_bus)
    sv.run_submission(TaskSubmission(name="t", capability="echo", input={"message": "hi"}))
    assert mock_bus.emit.call_count == 2
