"""HTTP capability for simple outbound API or page requests."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)
from engine.interfaces.task import RiskLevel


class HttpInput(BaseModel):
    method: Literal["GET", "POST"] = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    json_body: dict[str, Any] | None = None
    timeout_seconds: float = 10.0


class HttpCapability(Capability):
    input_model = HttpInput

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="http",
            description="Perform simple HTTP GET or POST requests.",
            risk_level=RiskLevel.MEDIUM,
            tags=["network", "api"],
        )

    def execute(
        self,
        payload: BaseModel | dict[str, Any],
        context: CapabilityContext,
    ) -> CapabilityResult:
        request = payload if isinstance(payload, HttpInput) else HttpInput.model_validate(payload)
        response = httpx.request(
            method=request.method,
            url=request.url,
            headers=request.headers,
            json=request.json_body,
            timeout=request.timeout_seconds,
        )
        response.raise_for_status()
        return CapabilityResult(
            output={
                "url": str(response.url),
                "status_code": response.status_code,
                "text": response.text,
            },
            metadata={"task_id": context.task_id},
        )
