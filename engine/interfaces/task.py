"""Generic task contracts for the minimal Conductor Engine runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=UTC)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    POLICY_DENIED = "policy_denied"
    CANCELLED = "cancelled"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskSubmission(BaseModel):
    """Input used to create an executable task."""

    name: str
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 0


class TaskResult(BaseModel):
    """Execution outcome persisted for completed or failed tasks."""

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AuditEntry(BaseModel):
    """A single recorded state transition on a task."""

    timestamp: datetime = Field(default_factory=_now)
    actor: str  # who or what caused the transition, e.g. "supervisor", "user", "policy"
    action: str  # description, e.g. "status_change", "retry", "approved"
    from_status: TaskStatus | None = None
    to_status: TaskStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    """Stored task document for the minimal runtime."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: TaskResult | None = None
    attempt: int = 0
    max_retries: int = 0
    workflow_id: str | None = None
    archived_at: datetime | None = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
