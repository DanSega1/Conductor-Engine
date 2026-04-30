"""Default retry strategy implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.interfaces.retry import (
    EscalationConfig,
    EscalationRecord,
    FailureContext,
    RetryDecision,
)

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

    def __init__(
        self,
        *,
        enable_escalation: bool = False,
        escalation_config: EscalationConfig | None = None,
    ) -> None:
        self.enable_escalation = enable_escalation
        self.escalation_config = escalation_config

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        """Decide retry based on attempt count and escalation config."""
        # Use escalation threshold if configured, otherwise fall back to task max_retries
        max_retries = failure.max_retries
        if self.escalation_config and self.escalation_config.max_retries_before_escalate is not None:
            max_retries = self.escalation_config.max_retries_before_escalate

        if failure.attempt > max_retries:
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=self.enable_escalation,
            )
        return RetryDecision(
            should_retry=True,
            reason=f"Retry {failure.attempt} of {max_retries}",
        )


class ThresholdEscalationPolicy:
    """Escalate after a configured number of failures.

    Default policy: escalates when failure count reaches or exceeds
    max_retries_before_escalate threshold.
    """

    def __init__(self, config: EscalationConfig) -> None:
        self.config = config

    def should_escalate(self, task: TaskRecord, history: list[FailureContext]) -> bool:
        """Escalate if failure count meets or exceeds threshold."""
        threshold = self.config.max_retries_before_escalate
        if threshold is None:
            threshold = task.max_retries
        return len(history) >= threshold

    def build_record(self, task: TaskRecord, history: list[FailureContext]) -> EscalationRecord:
        """Build escalation record with full failure history."""
        return EscalationRecord(
            task_id=task.task_id,
            capability=task.capability,
            total_attempts=len(history),
            failure_history=history,
            reason=self.config.escalation_reason,
            metadata=dict(self.config.escalation_metadata),
        )
