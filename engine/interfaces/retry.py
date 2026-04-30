"""Retry strategy contracts for behavioral retry and recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=UTC)


class FailureContext(BaseModel):
    """Structured context from a failed task attempt.

    Captured before retry decisions to provide observable failure history
    and enable behavioral retry strategies beyond blind repetition.
    """

    task_id: str
    capability: str
    attempt: int
    max_retries: int
    error_type: str
    error_message: str
    input_fingerprint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryDecision(BaseModel):
    """Decision from a retry strategy on how to proceed after failure."""

    should_retry: bool
    delay_seconds: float | None = None
    adjusted_input: dict[str, Any] | None = None
    reason: str | None = None
    escalate: bool = False


class EscalationConfig(BaseModel):
    """Configuration for task escalation behavior.

    Controls when and how tasks are escalated instead of marked as failed.
    """

    max_retries_before_escalate: int | None = None
    escalation_reason: str | None = None
    escalation_metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationRecord(BaseModel):
    """Structured record of a task escalation.

    Persisted as the task result when a task escalates, providing
    full audit trail of failures leading to escalation.
    """

    task_id: str
    capability: str
    total_attempts: int
    failure_history: list[FailureContext]
    escalated_at: datetime = Field(default_factory=_now)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryStrategy(Protocol):
    """Contract for retry decision logic.

    Implementations decide whether to retry, adjust inputs, or escalate
    based on accumulated failure context.
    """

    def decide(self, task: Any, failure: FailureContext) -> RetryDecision:
        """Evaluate failure and determine retry action.

        Args:
            task: TaskRecord for the failed task (typed as Any to avoid circular import)
            failure: Structured context from the failed attempt

        Returns:
            RetryDecision indicating whether to retry and how
        """
        ...


class EscalationPolicy(Protocol):
    """Contract for escalation decision logic.

    Separate from RetryStrategy to allow independent composition.
    """

    def should_escalate(self, task: Any, history: list[FailureContext]) -> bool:
        """Determine if task should escalate based on failure history.

        Args:
            task: TaskRecord for the failed task (typed as Any to avoid circular import)
            history: Accumulated failure contexts from all attempts

        Returns:
            True if task should escalate, False to continue normal retry/fail flow
        """
        ...

    def build_record(self, task: Any, history: list[FailureContext]) -> EscalationRecord:
        """Build escalation record for audit trail.

        Args:
            task: TaskRecord being escalated
            history: Accumulated failure contexts from all attempts

        Returns:
            EscalationRecord to persist as task result
        """
        ...
