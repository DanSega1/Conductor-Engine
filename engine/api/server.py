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
    api_key_path: str | Path | None = None,
    workdir: str | Path | None = None,
    log_level: str = "info",
    reload: bool = False,
    cors_origins: list[str] | None = None,
    tls_cert: str | Path | None = None,
    tls_key: str | Path | None = None,
    policy: str | None = None,
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
    api_key_path:
        Path to the API key store JSON file.  When provided and non-empty,
        all API endpoints require ``Authorization: Bearer <key>``.
        Defaults to ``.conductor/api_keys.json`` when *tls_cert* is set.
    workdir:
        Working directory for capability execution.  Defaults to cwd.
    log_level:
        Uvicorn log level (``"debug"``, ``"info"``, ``"warning"``, ``"error"``).
    reload:
        Enable uvicorn auto-reload (development only).
    cors_origins:
        Allowed CORS origins.  Defaults to ``["*"]`` (open for local dev).
        When *tls_cert* is set and no explicit value is given, defaults to
        an empty list (no CORS).
    tls_cert:
        Path to a TLS certificate file.  When set, the server serves HTTPS
        instead of HTTP.  Requires *tls_key*.
    tls_key:
        Path to the TLS private key file.  Required when *tls_cert* is set.
    policy:
        Policy mode string (``"default"``, ``"risk"``, or ``"deny-all"``).
        Defaults to ``"risk"`` (RiskLevelPolicyEngine with deny_above=HIGH)
        in serve mode.
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "The API server requires additional dependencies. "
            "Install with: pip install conductor-engine[api]"
        ) from exc

    from engine.api.app import create_api_app
    from engine.api.auth import load_api_key_store
    from engine.api.bus import SSEEventBus
    from engine.loader import load_capabilities
    from engine.runtime.policy import NullPolicyEngine, RiskLevelPolicyEngine
    from engine.runtime.queue import BoundedTaskQueue
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

    # Policy — Phase 7: default to RiskLevelPolicyEngine (deny_above=HIGH)
    if policy == "deny-all" or policy == "deny":
        from engine.runtime.policy import DenyByDefaultPolicy
        policy_engine = DenyByDefaultPolicy(allowed_capabilities=frozenset())
    elif policy == "null" or policy == "default":
        policy_engine = NullPolicyEngine()
    else:
        policy_engine = RiskLevelPolicyEngine(
            deny_above="high",
            require_approval_at="critical",
        )

    # Queue — Phase 7: bounded queue with backpressure
    queue = BoundedTaskQueue(max_size=1024)

    supervisor = TaskSupervisor(
        registry=registry,
        store=store,
        workdir=resolved_workdir,
        event_bus=event_bus,
        policy_engine=policy_engine,
        queue=queue,
    )

    # Wire up stub workflow orchestrator (same as `cond workflow run`)
    orchestrator = WorkflowOrchestrator(
        planner=LinearPlanner(steps=[]),
        worker=PassthroughWorker(),
        validator=PassthroughValidator(),
        supervisor=supervisor,
    )

    # API key store — auto-enable when TLS is configured
    resolved_api_key_path: str | Path | None = api_key_path
    if resolved_api_key_path is None and tls_cert is not None:
        resolved_api_key_path = resolved_workdir / ".conductor" / "api_keys.json"
    api_key_store = load_api_key_store(resolved_api_key_path)

    # CORS — tighten when TLS is active
    resolved_cors = cors_origins
    if resolved_cors is None and tls_cert is not None:
        resolved_cors = []  # no CORS for HTTPS deployments

    app = create_api_app(
        supervisor=supervisor,
        registry=registry,
        store=store,
        event_bus=event_bus,
        orchestrator=orchestrator,
        api_key_store=api_key_store,
        cors_origins=resolved_cors,
    )

    scheme = "https" if tls_cert else "http"
    print(f"Conductor Engine API  →  {scheme}://{host}:{port}/docs")

    uvicorn_kwargs: dict = {
        "app": app,
        "host": host,
        "port": port,
        "log_level": log_level,
        "reload": reload,
    }
    if tls_cert and tls_key:
        uvicorn_kwargs["ssl_certfile"] = str(tls_cert)
        uvicorn_kwargs["ssl_keyfile"] = str(tls_key)

    uvicorn.run(**uvicorn_kwargs)
