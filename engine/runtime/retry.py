"""Default retry strategy implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.interfaces.retry import FailureContext, RetryDecision

if TYPE_CHECKING:
    from engine.interfaces.task import TaskRecord


class DefaultRetryStrategy:
    """Retry while attempts remain; optionally escalate when exhausted.

    Preserves existing supervisor behavior:
    - Retry if attempt <= max_retries
    - No input adjustment (same input for every retry)
    - No delay between retries
    - Escalation is opt-in via enable_escalation flag
    """

    def __init__(self, *, enable_escalation: bool = False) -> None:
        self.enable_escalation = enable_escalation

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        """Decide retry based on attempt count and escalation config."""
        if failure.attempt > failure.max_retries:
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=self.enable_escalation,
            )
        return RetryDecision(
            should_retry=True,
            reason=f"Retry {failure.attempt} of {failure.max_retries}",
        )
