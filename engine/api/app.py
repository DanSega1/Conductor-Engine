"""FastAPI application factory.

Usage
-----
Minimal (no SSE, no workflow orchestrator, no cluster):

    from engine.api import create_api_app
    from engine.supervisor.service import TaskSupervisor
    from engine.registry.capabilities import CapabilityRegistry
    from engine.runtime.store import LocalTaskStore

    store = LocalTaskStore(".conductor/tasks.json")
    registry = CapabilityRegistry()
    supervisor = TaskSupervisor(registry=registry, store=store)
    app = create_api_app(supervisor=supervisor, registry=registry, store=store)

With SSE event streaming:

    from engine.api.bus import SSEEventBus

    bus = SSEEventBus()
    supervisor = TaskSupervisor(..., event_bus=bus)
    app = create_api_app(..., event_bus=bus)

With multi-engine cluster routing:

    from engine.api.cluster.registry import EngineRegistry

    cluster = EngineRegistry()
    app = create_api_app(..., cluster_registry=cluster)

With workflow orchestration:

    from engine.workflow.orchestrator import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(...)
    app = create_api_app(..., orchestrator=orchestrator)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.api.bus import SSEEventBus
from engine.api.cluster import routes as cluster_routes
from engine.api.cluster.registry import EngineRegistry
from engine.api.routes import capabilities, events, health, tasks, workflows
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import TaskStore
from engine.supervisor.service import TaskSupervisor

_DESCRIPTION = """\
## Conductor Engine API

Control-plane HTTP API for the Conductor orchestration runtime.

### Consumers

| Consumer | How it uses the API |
|----------|---------------------|
| **condor-tui** | Polls `/v1/snapshot`, subscribes to `/v1/events` SSE stream |
| **Wrapper services** | Submits tasks, approves/cancels, reads audit trails |
| **Fleet coordinator** | Registers engines at `/v1/engines`, routes tasks across nodes |
| **Web UI (future)** | Same surface as TUI, over HTTP/JSON |
| **MCP layer (future)** | May wrap task submission as MCP tool calls |

### Auth

Authentication is an open placeholder in this release (Phase 4).
Phase 7 will add JWT / API-key enforcement via the `get_auth_context`
dependency without changing any route handlers.

### Multi-engine

Register remote Conductor Engine instances at `POST /v1/engines`.
Route tasks to the best matching node at `POST /v1/engines/tasks/run`
using tag-based constraints (`pool`, `region`, `nodepool`, etc.).

### Event streaming

Subscribe to live task lifecycle events at `GET /v1/events` using
Server-Sent Events (SSE).  Compatible with `EventSource`, `curl -N`,
and any SSE client library.
"""


def create_api_app(
    *,
    supervisor: TaskSupervisor,
    registry: CapabilityRegistry,
    store: TaskStore,
    event_bus: SSEEventBus | None = None,
    orchestrator: Any | None = None,
    cluster_registry: EngineRegistry | None = None,
    title: str = "Conductor Engine",
    version: str = "v1",
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the Conductor Engine FastAPI application.

    Parameters
    ----------
    supervisor:
        The ``TaskSupervisor`` instance that handles task execution.
    registry:
        The ``CapabilityRegistry`` loaded with the capabilities for this instance.
    store:
        The ``TaskStore`` used for task persistence.
    event_bus:
        Optional ``SSEEventBus``.  When provided, ``GET /v1/events`` streams
        live task lifecycle events.  When None, the endpoint returns 503.
    orchestrator:
        Optional ``WorkflowOrchestrator``.  When provided, ``POST /v1/workflows``
        is available.  When None, the endpoint returns 501.
    cluster_registry:
        Optional ``EngineRegistry`` for multi-engine fleet management.
        Defaults to a new in-memory registry (always present; nodes register at runtime).
    title:
        API title shown in OpenAPI docs.
    version:
        Semantic version string shown in OpenAPI docs.
    cors_origins:
        List of allowed CORS origins.  Defaults to ``["*"]`` (open) for local
        development.  Restrict in production deployments.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Attach the running asyncio event loop to the SSE bus so that
        # supervisor threads can safely schedule queue puts from synchronous code.
        if app.state.event_bus is not None:
            app.state.event_bus.attach_loop(asyncio.get_running_loop())
        yield
        # Graceful shutdown: notify all SSE subscribers to stop iterating.
        if app.state.event_bus is not None:
            app.state.event_bus.shutdown()

    app = FastAPI(
        title=title,
        version=version,
        description=_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ------------------------------------------------------------------
    # State injection — shared across all requests
    # ------------------------------------------------------------------
    app.state.supervisor = supervisor
    app.state.registry = registry
    app.state.store = store
    app.state.event_bus = event_bus
    app.state.orchestrator = orchestrator
    app.state.cluster_registry = cluster_registry or EngineRegistry()

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    allowed_origins = cors_origins if cors_origins is not None else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Exception handlers — consistent error envelope
    # ------------------------------------------------------------------

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        return JSONResponse(
            status_code=status,
            content={"code": "invalid_request", "message": msg},
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"code": "not_found", "message": str(exc)},
        )

    # ------------------------------------------------------------------
    # Routes — all under /v1/
    # ------------------------------------------------------------------
    app.include_router(tasks.router, prefix="/v1")
    app.include_router(workflows.router, prefix="/v1")
    app.include_router(capabilities.router, prefix="/v1")
    app.include_router(health.router, prefix="/v1")
    app.include_router(events.router, prefix="/v1")
    app.include_router(cluster_routes.router, prefix="/v1")

    # ------------------------------------------------------------------
    # Root redirect
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def root():
        return {"service": "conductor-engine", "docs": "/docs", "api_version": "v1"}

    return app
