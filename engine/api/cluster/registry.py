"""Engine node registry for multi-engine fleet management.

The ``EngineRegistry`` tracks remote Conductor Engine instances that have
registered with this coordinator.  It is deliberately in-memory — nodes
re-register on startup and the registry rebuilds automatically.

For persistent node registration across coordinator restarts, back this with
a ``TaskStore``-compatible backend (Phase 7).

Design intent
-------------
This is NOT a replacement for Kubernetes or a service-mesh.  It is a
lightweight routing layer that lets a single ``cond serve`` instance act as
a coordinator for a fleet of engine workers.  Think Karpenter node-pool
routing at the application level:

  ┌──────────────────────────────────┐
  │  Conductor Coordinator           │
  │  POST /v1/engines (register)     │
  │  POST /v1/engines/{id}/tasks     │ ← routes to best matching node
  └────────────┬─────────────────────┘
               │ httpx proxy
       ┌───────┼───────┐
       ▼       ▼       ▼
  Engine-A  Engine-B  Engine-C
  (gpu)     (cpu)     (high-mem)

Each node exposes the same ``/v1/`` API surface.  The coordinator proxies
task submissions to the most suitable node based on tag matching.
"""

from __future__ import annotations

from datetime import UTC, datetime
import threading
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=UTC)


class EngineNode(BaseModel):
    """A registered remote Conductor Engine instance."""

    engine_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    base_url: str = Field(description="Base HTTP URL, e.g. http://10.0.0.5:8080")
    tags: dict[str, str] = Field(default_factory=dict)
    capabilities: list[str] = Field(
        default_factory=list,
        description="Capability names this runner supports (from its registry).",
    )
    registered_at: datetime = Field(default_factory=_now)
    last_seen: datetime = Field(default_factory=_now)
    healthy: bool = True

    def matches_tags(self, required: dict[str, str]) -> bool:
        """Return True if this node satisfies all required tag constraints."""
        return all(self.tags.get(k) == v for k, v in required.items())

    def has_capability(self, name: str) -> bool:
        """Return True if this node advertises support for *name*."""
        return name in self.capabilities


class EngineRegistry:
    """In-memory registry of registered engine nodes.

    Thread-safe: all mutations are protected by a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, EngineNode] = {}

    def register(self, node: EngineNode) -> EngineNode:
        """Register or re-register a node.  Returns the stored node."""
        with self._lock:
            self._nodes[node.engine_id] = node
        return node

    def deregister(self, engine_id: str) -> None:
        """Remove a node from the registry.  Silently ignores unknown IDs."""
        with self._lock:
            self._nodes.pop(engine_id, None)

    def get(self, engine_id: str) -> EngineNode | None:
        """Return a node by ID, or None if not registered."""
        with self._lock:
            return self._nodes.get(engine_id)

    def list(self) -> list[EngineNode]:
        """Return all registered nodes, sorted by name."""
        with self._lock:
            return sorted(self._nodes.values(), key=lambda n: n.name)

    def heartbeat(self, engine_id: str, *, healthy: bool = True) -> EngineNode | None:
        """Update ``last_seen`` and health status for a node.

        Returns the updated node, or None if the engine_id is unknown.
        """
        with self._lock:
            node = self._nodes.get(engine_id)
            if node is None:
                return None
            node.last_seen = _now()
            node.healthy = healthy
            return node

    def select(self, *, tags: dict[str, str] | None = None) -> list[EngineNode]:
        """Return all healthy nodes matching the given tag constraints.

        When ``tags`` is None or empty, all healthy nodes are returned.
        Results are sorted by ``last_seen`` descending (most recently active first).
        """
        with self._lock:
            nodes = list(self._nodes.values())

        healthy = [n for n in nodes if n.healthy]
        if tags:
            healthy = [n for n in healthy if n.matches_tags(tags)]
        return sorted(healthy, key=lambda n: n.last_seen, reverse=True)
