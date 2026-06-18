"""FastAPI dependency providers.

All route handlers receive their collaborators through these ``Depends``
callables rather than importing from module-level globals.  This makes
every endpoint independently testable by overriding dependencies on the
test ``TestClient``.

Auth:
    Authentication is enforced by ``AuthMiddleware`` (see ``app.py``),
    which validates the ``Authorization: Bearer <key>`` header and sets
    ``request.state.auth_context``.  The ``get_auth_context`` dependency
    below reads that value so route handlers don't need to repeat the
    validation logic.

    When the API key store is empty, the middleware passes all requests
    through with a default ``AuthContext(actor="api", scopes=["*"])``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from engine.api.auth import ApiKeyStore
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


def get_api_key_store(request: Request) -> ApiKeyStore:
    """Return the ApiKeyStore bound to this server instance."""
    return request.app.state.api_key_store


# ---------------------------------------------------------------------------
# Auth — Phase 7 middleware-based implementation
# ---------------------------------------------------------------------------


class AuthContext:
    """Caller identity resolved by the global auth middleware.

    Populated from the ``Authorization: Bearer <key>`` header by
    ``AuthMiddleware`` and stored on ``request.state.auth_context``.
    """

    def __init__(self, actor: str = "api", scopes: list[str] | None = None) -> None:
        self.actor = actor
        self.scopes = scopes or ["*"]

    def require_scope(self, scope: str) -> None:
        """Raise 403 if the caller lacks the required scope.

        A scope of ``"*"`` (wildcard) matches everything.
        """
        if "*" in self.scopes:
            return
        if scope not in self.scopes:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": f"Caller '{self.actor}' lacks required scope '{scope}'",
                    "required_scope": scope,
                    "caller_scopes": self.scopes,
                },
            )


def get_auth_context(request: Request) -> AuthContext:
    """Return the ``AuthContext`` set by the global auth middleware.

    The middleware (``AuthMiddleware`` in ``app.py``) validates the
    ``Authorization`` header and stores the result on
    ``request.state.auth_context``.  This dependency simply reads it.

    If the middleware is not installed (e.g. in some test setups),
    an open ``AuthContext(actor="api")`` is returned for compatibility.
    """
    ctx: AuthContext | None = getattr(request.state, "auth_context", None)
    if ctx is not None:
        return ctx
    return AuthContext(actor="api", scopes=["*"])


# Convenience annotated types for route signatures
SupervisorDep = Annotated[TaskSupervisor, Depends(get_supervisor)]
RegistryDep = Annotated[CapabilityRegistry, Depends(get_registry)]
StoreDep = Annotated[TaskStore, Depends(get_store)]
EventBusDep = Annotated[SSEEventBus, Depends(require_event_bus)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
