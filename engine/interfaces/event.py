"""Event contracts for the Conductor Engine observable execution model."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from engine.interfaces.task import TaskStatus


def _now() -> datetime:
    return datetime.now(tz=UTC)


class EventType(StrEnum):
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRY = "task_retry"
    TASK_POLICY_DENIED = "task_policy_denied"
    TASK_AWAITING_APPROVAL = "task_awaiting_approval"
    TASK_APPROVED = "task_approved"
    TASK_CANCELLED = "task_cancelled"


class TaskEvent(BaseModel):
    """Structured event emitted at each task state transition."""

    event_type: EventType
    task_id: str
    task_name: str
    capability: str
    status: TaskStatus
    attempt: int
    timestamp: datetime = Field(default_factory=_now)
    workflow_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventBus(Protocol):
    """Contract for receiving task lifecycle events."""

    def emit(self, event: TaskEvent) -> None:
        """Publish a task event to the bus."""
