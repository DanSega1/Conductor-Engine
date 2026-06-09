"""Capability interfaces and execution context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from engine.interfaces.task import RiskLevel


class CapabilityDescriptor(BaseModel):
    """Human- and machine-readable capability metadata."""

    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    tags: list[str] = Field(default_factory=list)
    require_approval: bool = Field(
        default=False,
        description=(
            "When True, every task using this capability is automatically routed to "
            "AWAITING_APPROVAL before execution, regardless of the policy engine decision. "
            "This is evaluated in the supervisor before the policy engine is consulted."
        ),
    )


class CapabilityContext(BaseModel):
    """Runtime context made available to every capability invocation."""

    task_id: str
    task_name: str
    workdir: str


class CapabilityResult(BaseModel):
    """Normalized result returned by capability implementations."""

    output: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityExecutionControls(BaseModel):
    """Runtime-configured execution controls applied by the supervisor."""

    timeout_seconds: float | None = Field(default=None, gt=0)
    min_interval_seconds: float | None = Field(default=None, ge=0)


class Capability(ABC):
    """Base class for all runtime capabilities."""

    input_model: type[BaseModel] | None = None

    def __init__(self, **config: Any) -> None:
        self.config = config

    @property
    @abstractmethod
    def descriptor(self) -> CapabilityDescriptor:
        """Return static metadata describing the capability."""

    def validate_input(self, payload: dict[str, Any]) -> BaseModel | dict[str, Any]:
        """Validate and normalize capability input before execution."""
        if self.input_model is None:
            return payload
        return self.input_model.model_validate(payload)

    def man_page(self) -> str | None:
        """Return an optional manual page body for CLI help output."""
        return None

    @abstractmethod
    def execute(
        self,
        payload: BaseModel | dict[str, Any],
        context: CapabilityContext,
    ) -> CapabilityResult:
        """Execute the capability and return a normalized result."""
