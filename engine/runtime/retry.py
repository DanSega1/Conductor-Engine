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

    escalation_threshold:
        When set alongside enable_escalation=True, escalation only triggers
        once failure.attempt >= escalation_threshold. Attempts below the
        threshold still produce a plain FAILED outcome rather than ESCALATED.
        When None (default), any exhaustion triggers escalation (if enabled).
    """

    def __init__(
        self,
        *,
        enable_escalation: bool = False,
        escalation_threshold: int | None = None,
    ) -> None:
        self.enable_escalation = enable_escalation
        self.escalation_threshold = escalation_threshold

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        """Decide retry based on attempt count and escalation config."""
        if failure.attempt > failure.max_retries:
            should_escalate = self.enable_escalation and (
                self.escalation_threshold is None
                or failure.attempt >= self.escalation_threshold
            )
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=should_escalate,
            )
        return RetryDecision(
            should_retry=True,
            reason=f"Retry {failure.attempt} of {failure.max_retries}",
        )
