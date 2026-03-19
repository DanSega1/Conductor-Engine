"""Memory contracts for optional engine-integrated long-term memory backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MemoryDocument(BaseModel):
    """Document to be stored in a memory backend."""

    external_id: str
    namespace: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class MemoryQuery(BaseModel):
    """Memory retrieval request."""

    query: str
    namespaces: list[str] = Field(default_factory=list)
    limit: int = 5
    metadata_filters: dict[str, Any] = Field(default_factory=dict)


class MemoryHit(BaseModel):
    """Normalized retrieval hit from a memory backend."""

    external_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None


@runtime_checkable
class MemoryProvider(Protocol):
    """Async memory backend contract used by apps and memory capabilities."""

    async def memorize(self, documents: list[MemoryDocument]) -> list[dict[str, Any]]:
        """Persist one or more documents and return backend-native summaries."""

    async def retrieve(self, query: MemoryQuery) -> list[MemoryHit]:
        """Return relevant hits for the supplied query."""
