"""MCP capability seam for addon packages.

The core engine owns the Capability contract. Concrete MCP transport wiring belongs in
an addon package such as conductor-mcp, which can inject the executor used here.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)
from engine.interfaces.task import RiskLevel


class MCPToolCall(BaseModel):
    """Tool invocation payload accepted by MCPCapability."""

    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolExecutor(Protocol):
    """Injected executor used by addon packages to bridge into an MCP transport."""

    def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: CapabilityContext,
    ) -> CapabilityResult | dict[str, Any] | Any:
        ...


class MCPCapability(Capability):
    """Capability wrapper around an injected MCP tool executor."""

    input_model = MCPToolCall

    def __init__(
        self,
        *,
        tool_name: str,
        executor: MCPToolExecutor,
        name: str | None = None,
        description: str | None = None,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        tags: list[str] | None = None,
        **config: Any,
    ) -> None:
        super().__init__(**config)
        self._tool_name = tool_name
        self._executor = executor
        self._descriptor = CapabilityDescriptor(
            name=name or tool_name,
            description=description or f"Invoke MCP tool '{tool_name}' via an injected executor.",
            risk_level=risk_level,
            tags=list(tags or ["mcp"]),
        )

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return self._descriptor

    def man_page(self) -> str | None:
        return (
            "Wraps an injected MCP tool executor. Transport setup, client sessions, and server "
            "lifecycle belong in an addon such as conductor-mcp."
        )

    def execute(self, payload: MCPToolCall, context: CapabilityContext) -> CapabilityResult:
        result = self._executor(self._tool_name, payload.arguments, context)
        if isinstance(result, CapabilityResult):
            return result
        if isinstance(result, dict) and set(result.keys()).issubset({"output", "metadata"}):
            return CapabilityResult(
                output=result.get("output"),
                metadata=dict(result.get("metadata", {})),
            )
        return CapabilityResult(output=result)
