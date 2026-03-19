"""Optional memory capability backed by a configured MemoryProvider."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)
from engine.interfaces.memory import MemoryDocument, MemoryProvider, MemoryQuery
from engine.interfaces.task import RiskLevel
from engine.memory.providers.memu import MemUProvider
from engine.runtime.async_utils import run_coro


class MemoryCapabilityRequest(BaseModel):
    action: Literal["memorize", "retrieve"]
    documents: list[MemoryDocument] = Field(default_factory=list)
    query: MemoryQuery | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> MemoryCapabilityRequest:
        if self.action == "memorize" and not self.documents:
            raise ValueError("documents is required for memorize actions")
        if self.action == "retrieve" and self.query is None:
            raise ValueError("query is required for retrieve actions")
        return self


class MemoryCapability(Capability):
    """Capability wrapper around an async memory provider."""

    input_model = MemoryCapabilityRequest

    def __init__(
        self,
        *,
        provider: MemoryProvider | None = None,
        provider_type: str = "memu",
        service_config: dict[str, Any] | None = None,
        scope: dict[str, Any] | None = None,
        **config: Any,
    ) -> None:
        merged_service_config = dict(service_config or {})
        if isinstance(config.get("service_config"), dict):
            merged_service_config.update(config["service_config"])

        merged_scope = dict(scope or {})
        if isinstance(config.get("scope"), dict):
            merged_scope.update(config["scope"])

        super().__init__(
            provider_type=provider_type,
            service_config=merged_service_config,
            scope=merged_scope,
            **config,
        )

        if provider is not None:
            self.provider = provider
        elif provider_type == "memu":
            self.provider = MemUProvider(service_config=merged_service_config, scope=merged_scope)
        else:
            raise ValueError(f"Unsupported memory provider type: {provider_type}")

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="memory",
            description="Persist and retrieve long-term memory documents.",
            risk_level=RiskLevel.MEDIUM,
            tags=["memory", "knowledge"],
        )

    def execute(
        self,
        payload: BaseModel | dict[str, Any],
        context: CapabilityContext,
    ) -> CapabilityResult:
        request = (
            payload
            if isinstance(payload, MemoryCapabilityRequest)
            else MemoryCapabilityRequest.model_validate(payload)
        )

        if request.action == "memorize":
            output = run_coro(self.provider.memorize(request.documents))
        else:
            output = [
                hit.model_dump(mode="json")
                for hit in run_coro(self.provider.retrieve(request.query))
            ]

        return CapabilityResult(
            output=output,
            metadata={"task_id": context.task_id, "action": request.action},
        )
