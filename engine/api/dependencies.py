"""FastAPI dependency providers.

All route handlers receive their collaborators through these ``Depends``
callables rather than importing from module-level globals.  This makes
every endpoint independently testable by overriding dependencies on the
test ``TestClient``.

Auth hook:
    ``get_auth_context`` is a placeholder for Phase 7.  It currently
    returns ``None`` (open access).  Replace the implementation with JWT /
    API-key validation without touching any route handler.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from engine.api.bus import SSEEventBus
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import TaskStore
from engine.supervisor.service import TaskSupervisor

# ---------------------------------------------------------------------------
# Core engine collaborators
# ---------------------------------------------------------------------------


def get_supervisor(request: Request) -> TaskSupervisor:
    """Return the TaskSupervisor bound to this server instance."""
    return request.app.state.supervisor


def get_registry(request: Request) -> CapabilityRegistry:
    """Return the CapabilityRegistry for this server instance."""
    return request.app.state.registry


def get_store(request: Request) -> TaskStore:
    """Return the raw TaskStore (used by routes that need store-level access)."""
    return request.app.state.store


def get_event_bus(request: Request) -> SSEEventBus | None:
    """Return the SSEEventBus, or None if SSE is not configured."""
    return getattr(request.app.state, "event_bus", None)


def require_event_bus(
    bus: Annotated[SSEEventBus | None, Depends(get_event_bus)],
) -> SSEEventBus:
    """Like ``get_event_bus`` but raises 503 when not configured."""
    if bus is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "sse_unavailable", "message": "Event streaming is not configured on this server"},
        )
    return bus


def get_orchestrator(request: Request):
    """Return the WorkflowOrchestrator, or raise 501 if not configured."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "not_implemented",
                "message": "Workflow orchestrator is not configured on this server instance",
            },
        )
    return orchestrator


def get_cluster_registry(request: Request):
    """Return the EngineRegistry for multi-engine fleet management."""
    return request.app.state.cluster_registry


def get_trigger_service(request: Request):
    """Return the WebhookIngressService, or None if not configured."""
    return getattr(request.app.state, "trigger_service", None)


# ---------------------------------------------------------------------------
# Auth hook (Phase 7 placeholder)
# ---------------------------------------------------------------------------


class AuthContext:
    """Caller identity resolved from the incoming request.

    Phase 7 will populate this from JWT / API-key headers.  For now it is
    an open placeholder — every caller is treated as trusted.
    """

    def __init__(self, actor: str = "api") -> None:
        self.actor = actor
        self.scopes: list[str] = ["*"]

    def require_scope(self, scope: str) -> None:
        """Raise 403 if the caller lacks the required scope.

        Currently a no-op; will enforce real permissions in Phase 7.
        """
        # TODO(phase7): enforce real scope checks
        pass


def get_auth_context(request: Request) -> AuthContext:
    """Resolve the caller's identity from the request.

    Phase 7 placeholder — returns a fully-trusted ``AuthContext`` for now.
    Replace this implementation to add real authentication without touching
    any route handler.
    """
    # TODO(phase7): parse Bearer token / API key from request.headers
    return AuthContext(actor="api")


# Convenience annotated types for route signatures
SupervisorDep = Annotated[TaskSupervisor, Depends(get_supervisor)]
RegistryDep = Annotated[CapabilityRegistry, Depends(get_registry)]
StoreDep = Annotated[TaskStore, Depends(get_store)]
EventBusDep = Annotated[SSEEventBus, Depends(require_event_bus)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
