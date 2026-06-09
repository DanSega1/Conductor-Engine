"""Uvicorn server entrypoint for the Conductor Engine API.

Called by ``cond serve`` and usable directly for programmatic startup::

    from engine.api.server import serve

    serve(host="0.0.0.0", port=8080, store_path=".conductor/tasks.json")
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def serve(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    store_path: str | Path = ".conductor/tasks.json",
    capabilities_path: str | Path | None = None,
    workdir: str | Path | None = None,
    log_level: str = "info",
    reload: bool = False,
    cors_origins: list[str] | None = None,
) -> None:
    """Start the Conductor Engine API server.

    Builds the full engine stack (registry, store, supervisor, SSE bus,
    workflow orchestrator) and launches a uvicorn ASGI server.

    Parameters
    ----------
    host:
        Bind address.  Use ``"0.0.0.0"`` to accept connections from all
        interfaces.  Defaults to loopback for safety.
    port:
        TCP port to listen on.
    store_path:
        Path to the JSON task store file.  Created on first write.
    capabilities_path:
        Path to the capabilities YAML config.  Falls back to
        ``config/conductor.capabilities.yaml`` then built-ins.
    workdir:
        Working directory for capability execution.  Defaults to cwd.
    log_level:
        Uvicorn log level (``"debug"``, ``"info"``, ``"warning"``, ``"error"``).
    reload:
        Enable uvicorn auto-reload (development only).
    cors_origins:
        Allowed CORS origins.  Defaults to ``["*"]`` (open for local dev).
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "The API server requires additional dependencies. "
            "Install with: pip install conductor-engine[api]"
        ) from exc

    from engine.api.app import create_api_app
    from engine.api.bus import SSEEventBus
    from engine.loader import load_capabilities
    from engine.runtime.store import LocalTaskStore
    from engine.supervisor.service import TaskSupervisor
    from engine.workflow.agents import LinearPlanner, PassthroughValidator, PassthroughWorker
    from engine.workflow.orchestrator import WorkflowOrchestrator

    resolved_workdir = Path(workdir or Path.cwd()).resolve()
    resolved_store = Path(store_path)
    resolved_store.parent.mkdir(parents=True, exist_ok=True)

    # Build engine stack
    if capabilities_path:
        registry = load_capabilities(capabilities_path, base_path=resolved_workdir)
    else:
        _default_config = resolved_workdir / "config" / "conductor.capabilities.yaml"
        if _default_config.exists():
            registry = load_capabilities(_default_config, base_path=resolved_workdir)
        else:
            registry = load_capabilities(base_path=resolved_workdir)

    store = LocalTaskStore(resolved_store)
    event_bus = SSEEventBus()

    supervisor = TaskSupervisor(
        registry=registry,
        store=store,
        workdir=resolved_workdir,
        event_bus=event_bus,
    )

    # Wire up stub workflow orchestrator (same as `cond workflow run`)
    orchestrator = WorkflowOrchestrator(
        planner=LinearPlanner(steps=[]),
        worker=PassthroughWorker(),
        validator=PassthroughValidator(),
        supervisor=supervisor,
    )

    app = create_api_app(
        supervisor=supervisor,
        registry=registry,
        store=store,
        event_bus=event_bus,
        orchestrator=orchestrator,
        cors_origins=cors_origins,
    )

    print(f"Conductor Engine API  →  http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level=log_level, reload=reload)
