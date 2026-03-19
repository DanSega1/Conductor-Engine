"""Filesystem capability with a confined local root."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from engine.guardrails.validation import ensure_local_path
from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)
from engine.interfaces.task import RiskLevel


class FilesystemInput(BaseModel):
    action: Literal["read_text", "write_text", "list_dir"]
    path: str
    content: str | None = None
    encoding: str = Field(default="utf-8")


class FilesystemCapability(Capability):
    input_model = FilesystemInput

    def __init__(self, **config: object) -> None:
        super().__init__(**config)
        self.base_path = Path(str(self.config.get("base_path", Path.cwd()))).resolve()

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="filesystem",
            description="Read, write, and list files under a configured root path.",
            risk_level=RiskLevel.MEDIUM,
            tags=["io", "local"],
        )

    def validate_input(self, payload: dict[str, object]) -> BaseModel | dict[str, object]:
        request = FilesystemInput.model_validate(payload)
        ensure_local_path(request.path, self.base_path)
        return request

    def execute(
        self,
        payload: BaseModel | dict[str, object],
        context: CapabilityContext,
    ) -> CapabilityResult:
        request = (
            payload
            if isinstance(payload, FilesystemInput)
            else FilesystemInput.model_validate(payload)
        )
        target = ensure_local_path(request.path, self.base_path)

        if request.action == "read_text":
            return CapabilityResult(
                output={
                    "path": str(target),
                    "content": target.read_text(encoding=request.encoding),
                },
            )

        if request.action == "write_text":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(request.content or "", encoding=request.encoding)
            return CapabilityResult(
                output={
                    "path": str(target),
                    "bytes_written": len((request.content or "").encode()),
                },
                metadata={"actor": context.task_name},
            )

        entries = sorted(item.name for item in target.iterdir())
        return CapabilityResult(output={"path": str(target), "entries": entries})
