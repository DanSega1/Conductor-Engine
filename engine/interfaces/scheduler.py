"""Scheduler contracts for external trigger ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from engine.interfaces.task import TaskSubmission


def _now() -> datetime:
    return datetime.now(tz=UTC)


class TriggerSource(StrEnum):
    CRON = "cron"


class TriggerDispatch(BaseModel):
    """A single task submission emitted by an external trigger adapter."""

    dispatch_id: str = Field(default_factory=lambda: str(uuid4()))
    source: TriggerSource
    trigger_name: str
    scheduled_for: datetime
    emitted_at: datetime = Field(default_factory=_now)
    submission: TaskSubmission


class ExternalTriggerAdapter(Protocol):
    """Contract for adapters that emit task submissions from external systems."""

    def poll(self, *, now: datetime | None = None) -> list[TriggerDispatch]:
        """Return dispatches that should be submitted at the current time."""

    def health_check(self) -> list[str]:
        """Return adapter health issues; empty list means healthy."""
