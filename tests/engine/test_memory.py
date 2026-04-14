"""Tests for engine memory interfaces, provider mapping, and capability behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from engine.capabilities.memory import MemoryCapability, MemoryCapabilityRequest
from engine.interfaces.capability import CapabilityContext
from engine.interfaces.memory import MemoryDocument, MemoryHit, MemoryQuery
from engine.loader import load_capabilities_from_file
from engine.memory.providers.memu import MemUProvider


class FakeMemUService:
    def __init__(self, **config) -> None:
        self.config = config
        self.memorize_calls = []
        self.retrieve_calls = []

    async def memorize(self, **kwargs):
        self.memorize_calls.append(kwargs)
        return {"ok": True, "resource_url": kwargs["resource_url"]}

    async def retrieve(self, **kwargs):
        self.retrieve_calls.append(kwargs)
        return {
            "items": [
                {
                    "id": "item-1",
                    "content": "User prefers concise summaries",
                    "metadata": {"relative_path": "copilot-1.md"},
                    "user": {"namespace": "conversation"},
                    "score": 0.91,
                }
            ]
        }


def test_memory_capability_request_requires_documents_for_memorize() -> None:
    with pytest.raises(ValueError, match="documents is required"):
        MemoryCapabilityRequest(action="memorize")


def test_memu_provider_maps_documents_and_queries(tmp_path: Path) -> None:
    service = FakeMemUService()
    provider = MemUProvider(service=service, scope={"user_id": "scope-1"})
    source = tmp_path / "memory.md"
    source.write_text("Hello memory")

    document = MemoryDocument(
        external_id="conversation:memory.md",
        namespace="conversation",
        content="Hello memory",
        metadata={"source_path": str(source), "relative_path": "memory.md", "modality": "document"},
    )

    memorize_result = asyncio.run(provider.memorize([document]))
    hits = asyncio.run(
        provider.retrieve(MemoryQuery(query="preferences", namespaces=["conversation"], limit=3))
    )

    assert memorize_result[0]["external_id"] == "conversation:memory.md"
    assert service.memorize_calls[0]["user"] == {"user_id": "scope-1", "namespace": "conversation"}
    assert service.retrieve_calls[0]["where"] == {
        "user_id": "scope-1",
        "namespace__in": ["conversation"],
    }
    assert hits == [
        MemoryHit(
            external_id="item-1",
            content="User prefers concise summaries",
            metadata={
                "relative_path": "copilot-1.md",
                "user": {"namespace": "conversation"},
                "namespace": "conversation",
            },
            score=0.91,
        )
    ]


def test_memory_capability_uses_provider_for_retrieve() -> None:
    class FakeProvider:
        async def memorize(self, documents):  # pragma: no cover - unused
            return [{"documents": len(documents)}]

        async def retrieve(self, query):
            return [MemoryHit(external_id="1", content=query.query, metadata={"namespace": "pkm"})]

    capability = MemoryCapability(provider=FakeProvider())

    result = capability.execute(
        {"action": "retrieve", "query": {"query": "work habits", "namespaces": ["pkm"]}},
        CapabilityContext(task_id="task-1", task_name="memory search", workdir="."),
    )

    assert result.output == [
        {
            "external_id": "1",
            "content": "work habits",
            "metadata": {"namespace": "pkm"},
            "score": None,
        }
    ]


def test_memory_capability_runs_inside_active_event_loop() -> None:
    class FakeProvider:
        async def memorize(self, documents):  # pragma: no cover - unused
            return [{"documents": len(documents)}]

        async def retrieve(self, query):
            return [MemoryHit(external_id="loop-1", content=query.query, metadata={})]

    async def exercise() -> None:
        capability = MemoryCapability(provider=FakeProvider())

        result = capability.execute(
            {"action": "retrieve", "query": {"query": "async host", "namespaces": ["pkm"]}},
            CapabilityContext(task_id="task-2", task_name="memory search", workdir="."),
        )

        assert result.output[0]["external_id"] == "loop-1"
        assert result.output[0]["content"] == "async host"

    asyncio.run(exercise())


def test_load_capabilities_from_file_supports_memory_plugin(tmp_path: Path) -> None:
    config_path = tmp_path / "capabilities.yaml"
    config_path.write_text(
        "\n".join(
            [
                "include_builtins: false",
                "capabilities:",
                "  - import_path: engine.capabilities.memory:MemoryCapability",
                "    config:",
                "      provider_type: memu",
                "      service_config: {}",
                "      scope:",
                "        user_id: home-ai-control-plane",
            ]
        )
    )

    registry = load_capabilities_from_file(config_path, base_path=tmp_path)

    assert registry.names() == ["memory"]
