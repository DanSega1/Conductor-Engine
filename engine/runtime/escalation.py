"""Escalation policy implementations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from engine.interfaces.escalation import EscalationConfig, EscalationRecord
from engine.interfaces.retry import FailureContext

if TYPE_CHECKING:
    from engine.interfaces.task import TaskRecord


class ThresholdEscalationPolicy:
    """Escalates when accumulated failures reach the configured threshold.

    Checks after each retry decision. The escalation fires when the
    failure count is >= max_retries_before_escalate, giving the supervisor
    a chance to escalate before all retries are exhausted.
    """

    def __init__(self, config: EscalationConfig) -> None:
        self.config = config

    def should_escalate(self, task: TaskRecord, history: list[FailureContext]) -> bool:
        """Return True when failure count meets or exceeds the threshold."""
        return len(history) >= self.config.max_retries_before_escalate

    def build_record(self, task: TaskRecord, history: list[FailureContext]) -> EscalationRecord:
        """Build an escalation record with full failure history."""
        reason = self.config.escalation_reason or (
            f"Escalation threshold reached after {len(history)} failure(s)"
        )
        return EscalationRecord(
            task_id=task.task_id,
            capability=task.capability,
            total_attempts=task.attempt,
            failure_history=list(history),
            escalated_at=datetime.now(),
            reason=reason,
        )
