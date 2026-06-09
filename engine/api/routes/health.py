"""Health and snapshot routes.

Endpoints
---------
GET  /v1/health      Component health summary
GET  /v1/snapshot    Full versioned control-plane snapshot (JSON)
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from engine.api.dependencies import RegistryDep, StoreDep, SupervisorDep
from engine.control_plane.contracts import (
    ControlPlaneHealthComponentV1,
    ControlPlaneSnapshotV1,
    build_control_plane_snapshot,
    build_health_components,
)

router = APIRouter(tags=["observability"])


def _get_health_components(
    registry,
    store,
    supervisor,
) -> list[ControlPlaneHealthComponentV1]:
    queue = getattr(supervisor, "queue", None)
    event_bus = getattr(supervisor, "_bus", None)
    policy = getattr(supervisor, "_policy", None)

    components: list[tuple[str, object, str]] = [
        ("registry", registry, f"{len(registry.names())} capabilities loaded"),
        ("supervisor", supervisor, supervisor.workdir),
    ]
    if queue is not None:
        components.append(("queue", queue, f"{len(queue.list())} queued"))
    if event_bus is not None:
        components.append(("event_bus", event_bus, type(event_bus).__name__))
    if policy is not None:
        components.append(("policy", policy, type(policy).__name__))
    if hasattr(store, "path"):
        components.append(("task_store", store, str(store.path)))
    else:
        components.append(("task_store", store, type(store).__name__))

    return build_health_components(*components)


@router.get(
    "/health",
    summary="Health check",
    response_model=dict,
    responses={
        200: {"description": "All components healthy"},
        503: {"description": "One or more components report issues"},
    },
)
def health_check(
    request: Request,
    supervisor: SupervisorDep,
    registry: RegistryDep,
    store: StoreDep,
):
    """Return health status for every engine component.

    Returns HTTP 200 when all components are healthy, 503 when any report issues.

    Example response:
    ```json
    {
      "healthy": true,
      "components": [
        {"name": "registry", "healthy": true, "detail": "4 capabilities loaded", "issues": []},
        {"name": "supervisor", "healthy": true, "detail": "/path/to/workdir", "issues": []}
      ]
    }
    ```
    """
    components = _get_health_components(registry, store, supervisor)
    overall_healthy = all(c.healthy for c in components)

    from fastapi.responses import JSONResponse

    body = {
        "healthy": overall_healthy,
        "components": [c.model_dump() for c in components],
    }
    status_code = 200 if overall_healthy else 503
    return JSONResponse(content=body, status_code=status_code)


@router.get(
    "/snapshot",
    summary="Control-plane snapshot",
    response_model=dict,
    responses={200: {"description": "Full versioned v1 snapshot"}},
)
def get_snapshot(
    supervisor: SupervisorDep,
    registry: RegistryDep,
    store: StoreDep,
):
    """Emit a complete versioned control-plane snapshot.

    Contains all tasks, pending approvals, workflow traces, capabilities,
    and health components in a single stable ``v1`` envelope.

    This is the primary data source for TUI and monitoring tools.
    """
    health = _get_health_components(registry, store, supervisor)
    snapshot: ControlPlaneSnapshotV1 = build_control_plane_snapshot(
        tasks=supervisor.list_tasks(),
        registry=registry,
        health_components=health,
    )
    return snapshot.model_dump(mode="json")
