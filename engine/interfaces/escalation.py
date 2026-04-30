"""Escalation path contracts for first-class escalation in the runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from engine.interfaces.retry import FailureContext


class EscalationConfig(BaseModel):
    """Configuration for escalation behaviour.

    Defines when and how a task should be escalated after accumulated failures.
    """

    max_retries_before_escalate: int
    escalation_reason: str | None = None
    escalation_metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationRecord(BaseModel):
    """Structured record produced when a task escalates.

    Captured at escalation time to provide full failure history and
    context for downstream handling or alerting.
    """

    task_id: str
    capability: str
    total_attempts: int
    failure_history: list[FailureContext]
    escalated_at: datetime
    reason: str | None = None


class EscalationPolicy(Protocol):
    """Contract for escalation decision logic.

    Separate from RetryStrategy so callers can compose both independently.
    The supervisor checks this policy after each retry decision.
    """

    def should_escalate(self, task: Any, history: list[FailureContext]) -> bool:
        """Return True if the task should be escalated given its failure history."""
        ...

    def build_record(self, task: Any, history: list[FailureContext]) -> EscalationRecord:
        """Build a structured escalation record for the task."""
        ...
