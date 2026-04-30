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


class OPAInput(BaseModel):
    """Standard input bundle sent to an OPA REST endpoint.

    Serialises to the JSON shape that Conductor's built-in Rego policies expect:

        POST /v1/data/{policy_path}
        {"input": {<this model's fields>}}

    Rego policies can reference:
        input.task.{id,name,capability,input,max_retries,workflow_id}
        input.capability.{name,description,risk_level}
        input.workdir
    """

    task: dict[str, Any]
    capability: dict[str, Any]
    workdir: str

    @classmethod
    def from_context(cls, task: TaskRecord, context: PolicyContext) -> OPAInput:
        """Build an OPAInput from the supervisor's TaskRecord and PolicyContext."""
        return cls(
            task={
                "id": task.task_id,
                "name": task.name,
                "capability": task.capability,
                "input": task.input,
                "max_retries": task.max_retries,
                "workflow_id": task.workflow_id,
            },
            capability=context.capability.model_dump(),
            workdir=context.workdir,
        )


class PolicyEngine(Protocol):
    """Contract for authorizing a task before capability execution."""

    def evaluate(self, task: TaskRecord, context: PolicyContext) -> PolicyDecision:
        """Return the policy decision for a pending task."""
