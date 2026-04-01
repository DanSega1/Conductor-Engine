"""Shared interfaces for the Conductor Engine."""

from engine.interfaces.agent import AgentContext, AgentInterface, AgentResponse, AgentRole
from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)
from engine.interfaces.memory import MemoryDocument, MemoryHit, MemoryProvider, MemoryQuery
from engine.interfaces.task import RiskLevel, TaskRecord, TaskResult, TaskStatus, TaskSubmission
from engine.interfaces.workflow import (
    PlannerContext,
    PlannerInterface,
    PlanResponse,
    PlanStep,
    ValidationResponse,
    ValidatorContext,
    ValidatorInterface,
    WorkerContext,
    WorkerInterface,
    WorkerResponse,
    WorkflowGoal,
    WorkflowResult,
    WorkflowStatus,
)

__all__ = [
    "AgentContext",
    "AgentInterface",
    "AgentResponse",
    "AgentRole",
    "Capability",
    "CapabilityContext",
    "CapabilityDescriptor",
    "CapabilityResult",
    "MemoryDocument",
    "MemoryHit",
    "MemoryProvider",
    "MemoryQuery",
    "PlanResponse",
    "PlanStep",
    "PlannerContext",
    "PlannerInterface",
    "RiskLevel",
    "TaskRecord",
    "TaskResult",
    "TaskStatus",
    "TaskSubmission",
    "ValidationResponse",
    "ValidatorContext",
    "ValidatorInterface",
    "WorkerContext",
    "WorkerInterface",
    "WorkerResponse",
    "WorkflowGoal",
    "WorkflowResult",
    "WorkflowStatus",
]
