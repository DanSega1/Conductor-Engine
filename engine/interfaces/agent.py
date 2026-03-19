"""Logical agent interfaces for future planner/worker/validator layers."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    WORKER = "worker"
    VALIDATOR = "validator"


class AgentContext(BaseModel):
    task_id: str
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class AgentInterface(Protocol):
    """Common contract for future agent roles."""

    role: AgentRole

    def run(self, goal: str, context: AgentContext) -> AgentResponse:
        """Execute agent logic for the supplied goal and context."""
