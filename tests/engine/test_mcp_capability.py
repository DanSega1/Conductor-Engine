"""Tests for the MCP capability seam."""

from __future__ import annotations

from engine.capabilities.mcp import MCPCapability
from engine.interfaces.capability import CapabilityContext


def test_mcp_capability_delegates_to_injected_executor() -> None:
    calls: list[tuple[str, dict[str, str], str]] = []

    def executor(tool_name: str, arguments: dict[str, str], context: CapabilityContext):
        calls.append((tool_name, arguments, context.task_id))
        return {
            "output": {"ok": True, "tool": tool_name},
            "metadata": {"source": "test"},
        }

    capability = MCPCapability(
        tool_name="bookmark.add",
        executor=executor,
        name="bookmark-mcp",
        description="Bookmark bridge.",
    )

    payload = capability.validate_input({"arguments": {"url": "https://example.com"}})
    result = capability.execute(
        payload,
        CapabilityContext(task_id="task-1", task_name="bookmark", workdir="/tmp"),
    )

    assert capability.descriptor.name == "bookmark-mcp"
    assert result.output == {"ok": True, "tool": "bookmark.add"}
    assert result.metadata == {"source": "test"}
    assert calls == [("bookmark.add", {"url": "https://example.com"}, "task-1")]
