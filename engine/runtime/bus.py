"""EventBus implementations: NullEventBus (default) and LoggingEventBus."""

from __future__ import annotations

import logging

from engine.interfaces.event import EventType, TaskEvent

logger = logging.getLogger(__name__)


class NullEventBus:
    """No-op event bus. Default when no bus is configured.

    Zero overhead — emit() is a single-instruction no-op.
    Safe to use in all environments including tests.
    """

    def emit(self, event: TaskEvent) -> None:
        return


class LoggingEventBus:
    """Emits task events as structured log entries via Python's logging module.

    Each event is logged at INFO level (FAILED events at WARNING).
    Structured fields are included in the ``extra`` dict so log formatters
    and handlers can surface them in JSON, OTLP, or plain text.
    """

    def __init__(self, log: logging.Logger | None = None) -> None:
        self._log = log or logger

    def emit(self, event: TaskEvent) -> None:
        extra = {
            "event_type": event.event_type,
            "task_id": event.task_id,
            "task_name": event.task_name,
            "capability": event.capability,
            "status": event.status,
            "attempt": event.attempt,
            "workflow_id": event.workflow_id,
        }
        if event.event_type == EventType.TASK_FAILED:
            self._log.warning(
                "task_failed task_id=%s name=%s error=%s attempt=%d",
                event.task_id,
                event.task_name,
                event.error,
                event.attempt,
                extra=extra,
            )
        else:
            self._log.info(
                "%s task_id=%s name=%s attempt=%d",
                event.event_type,
                event.task_id,
                event.task_name,
                event.attempt,
                extra=extra,
            )
