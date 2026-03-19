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


class CapabilityContext(BaseModel):
    """Runtime context made available to every capability invocation."""

    task_id: str
    task_name: str
    workdir: str


class CapabilityResult(BaseModel):
    """Normalized result returned by capability implementations."""

    output: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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

    @abstractmethod
    def execute(
        self,
        payload: BaseModel | dict[str, Any],
        context: CapabilityContext,
    ) -> CapabilityResult:
        """Execute the capability and return a normalized result."""
