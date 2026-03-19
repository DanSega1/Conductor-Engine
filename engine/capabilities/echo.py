"""Echo capability used for smoke tests and examples."""

from __future__ import annotations

from pydantic import BaseModel

from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)


class EchoInput(BaseModel):
    message: str


class EchoCapability(Capability):
    input_model = EchoInput

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="echo",
            description="Return the provided message unchanged.",
            tags=["testing", "utility"],
        )

    def execute(
        self,
        payload: BaseModel | dict[str, object],
        context: CapabilityContext,
    ) -> CapabilityResult:
        data = payload if isinstance(payload, EchoInput) else EchoInput.model_validate(payload)
        return CapabilityResult(
            output={"message": data.message},
            metadata={"task_id": context.task_id},
        )
