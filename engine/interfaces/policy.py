"""Policy contracts for task authorization and approval gating."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from engine.interfaces.capability import CapabilityDescriptor
from engine.interfaces.task import TaskRecord


class PolicyDecisionType(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyContext(BaseModel):
    """Stable policy input derived from the runtime execution context."""

    capability: CapabilityDescriptor
    workdir: str


class PolicyDecision(BaseModel):
    """Normalized policy response consumed by the supervisor."""

    decision: PolicyDecisionType = PolicyDecisionType.ALLOW
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEngine(Protocol):
    """Contract for authorizing a task before capability execution."""

    def evaluate(self, task: TaskRecord, context: PolicyContext) -> PolicyDecision:
        """Return the policy decision for a pending task."""
