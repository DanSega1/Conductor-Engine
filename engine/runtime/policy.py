"""Runtime policy implementations."""

from __future__ import annotations

from engine.interfaces.policy import PolicyContext, PolicyDecision, PolicyDecisionType
from engine.interfaces.task import TaskRecord


class NullPolicyEngine:
    """Default policy engine that allows every task."""

    def evaluate(self, task: TaskRecord, context: PolicyContext) -> PolicyDecision:
        return PolicyDecision(decision=PolicyDecisionType.ALLOW)

    def health_check(self) -> list[str]:
        return []
