"""Retry strategy contracts for behavioral retry and recovery."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


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
