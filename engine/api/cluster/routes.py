"""Multi-engine cluster management routes.

Endpoints
---------
GET    /v1/engines                          List all registered engine nodes
POST   /v1/engines                          Register a new engine node
GET    /v1/engines/{engine_id}              Get a single node
DELETE /v1/engines/{engine_id}              Deregister a node
POST   /v1/engines/{engine_id}/heartbeat    Update last_seen / health status
GET    /v1/engines/{engine_id}/health       Proxy health check to remote node
GET    /v1/engines/{engine_id}/snapshot     Proxy full snapshot from remote node
POST   /v1/engines/{engine_id}/tasks/run    Submit + run task on a specific node
POST   /v1/engines/tasks/run               Auto-select best node and run task

Proxy behaviour
---------------
``/health`` and ``/snapshot`` endpoints are proxied to the remote engine's
own API using httpx (already a core dependency).  Responses are forwarded
as-is so the caller gets the same v1 contract shape regardless of which
node served the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
import httpx

from engine.api.cluster.registry import EngineNode, EngineRegistry
from engine.api.dependencies import get_cluster_registry
from engine.api.models import (
    EngineListResponse,
    EngineNodeResponse,
    RegisterEngineRequest,
    SubmitToEngineRequest,
)

router = APIRouter(prefix="/engines", tags=["cluster"])

_HTTP_TIMEOUT = 10.0  # seconds for proxied requests


def _node_to_response(node: EngineNode) -> EngineNodeResponse:
    return EngineNodeResponse(
        engine_id=node.engine_id,
        name=node.name,
        base_url=node.base_url,
        tags=node.tags,
        capabilities=node.capabilities,
        registered_at=node.registered_at.isoformat(),
        last_seen=node.last_seen.isoformat(),
        healthy=node.healthy,
    )


def _get_node_or_404(registry: EngineRegistry, engine_id: str) -> EngineNode:
    node = registry.get(engine_id)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Engine {engine_id!r} is not registered"},
        )
    return node


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="List registered engine nodes",
    response_model=EngineListResponse,
    responses={200: {"description": "All registered nodes"}},
)
def list_engines(
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
    tag: Annotated[
        list[str] | None,
        Query(description="Filter by tag (key=value). Repeat for multiple tags."),
    ] = None,
):
    """Return all registered engine nodes.

    Use ``?tag=pool=gpu&tag=region=us-east-1`` to filter by tag labels.

    Example response:
    ```json
    {
      "items": [
        {
          "engine_id": "...",
          "name": "worker-gpu-01",
          "base_url": "http://10.0.0.5:8080",
          "tags": {"pool": "gpu", "region": "us-east-1"},
          "healthy": true
        }
      ],
      "total": 1
    }
    ```
    """
    tag_filter: dict[str, str] = {}
    if tag:
        for t in tag:
            if "=" not in t:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "invalid_tag", "message": f"Tag must be key=value, got: {t!r}"},
                )
            k, v = t.split("=", 1)
            tag_filter[k] = v

    nodes = registry.select(tags=tag_filter if tag_filter else None)
    items = [_node_to_response(n) for n in nodes]
    return EngineListResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=201,
    summary="Register an engine node",
    response_model=EngineNodeResponse,
    responses={201: {"description": "Node registered"}},
)
def register_engine(
    body: RegisterEngineRequest,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Register a remote Conductor Engine instance with this coordinator.

    Call this from engine node startup scripts or node-pool managers.  The
    node will be available for task routing immediately after registration.

    Example request:
    ```json
    {
      "name": "worker-gpu-01",
      "base_url": "http://10.0.0.5:8080",
      "tags": {"pool": "gpu", "region": "us-east-1", "nodepool": "high-memory"}
    }
    ```
    """
    node = EngineNode(
        name=body.name,
        base_url=body.base_url.rstrip("/"),
        tags=body.tags,
        capabilities=body.capabilities,
    )
    registry.register(node)
    return _node_to_response(node)


# ---------------------------------------------------------------------------
# Get single node
# ---------------------------------------------------------------------------


@router.get(
    "/{engine_id}",
    summary="Get an engine node",
    response_model=EngineNodeResponse,
    responses={
        200: {"description": "Node detail"},
        404: {"description": "Node not registered"},
    },
)
def get_engine(
    engine_id: str,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Return registration detail for a single engine node."""
    node = _get_node_or_404(registry, engine_id)
    return _node_to_response(node)


# ---------------------------------------------------------------------------
# Deregister
# ---------------------------------------------------------------------------


@router.delete(
    "/{engine_id}",
    status_code=204,
    summary="Deregister an engine node",
    responses={
        204: {"description": "Node removed"},
        404: {"description": "Node not registered"},
    },
)
def deregister_engine(
    engine_id: str,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Remove an engine node from the registry.

    The node is no longer considered for task routing after this call.
    In-flight tasks on the node are not affected.
    """
    _get_node_or_404(registry, engine_id)
    registry.deregister(engine_id)


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


@router.post(
    "/{engine_id}/heartbeat",
    summary="Update engine heartbeat",
    response_model=EngineNodeResponse,
    responses={
        200: {"description": "Heartbeat recorded"},
        404: {"description": "Node not registered"},
    },
)
def engine_heartbeat(
    engine_id: str,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
    healthy: Annotated[bool, Query(description="Whether the node considers itself healthy")] = True,
):
    """Update a node's ``last_seen`` timestamp and health status.

    Call this from each engine node on a regular interval (e.g. every 30s)
    so the coordinator knows the node is still alive.
    """
    node = registry.heartbeat(engine_id, healthy=healthy)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Engine {engine_id!r} is not registered"},
        )
    return _node_to_response(node)


# ---------------------------------------------------------------------------
# Proxy: health
# ---------------------------------------------------------------------------


@router.get(
    "/{engine_id}/health",
    summary="Get health from a remote engine",
    response_model=dict,
    responses={
        200: {"description": "Health response from the remote node"},
        404: {"description": "Node not registered"},
        502: {"description": "Could not reach the remote node"},
    },
)
def get_engine_health(
    engine_id: str,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Proxy a health check to the specified remote engine node.

    Returns the same shape as ``GET /v1/health`` on the remote node.
    """
    node = _get_node_or_404(registry, engine_id)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.get(f"{node.base_url}/v1/health")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "proxy_error", "message": f"Could not reach engine {engine_id!r}: {exc}"},
        ) from exc


# ---------------------------------------------------------------------------
# Proxy: snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/{engine_id}/snapshot",
    summary="Get snapshot from a remote engine",
    response_model=dict,
    responses={
        200: {"description": "Control-plane snapshot from the remote node"},
        404: {"description": "Node not registered"},
        502: {"description": "Could not reach the remote node"},
    },
)
def get_engine_snapshot(
    engine_id: str,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Proxy a control-plane snapshot request to the specified remote engine.

    Returns the same ``ControlPlaneSnapshotV1`` shape as ``GET /v1/snapshot``
    on the remote node — same schema version, same field names.
    """
    node = _get_node_or_404(registry, engine_id)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.get(f"{node.base_url}/v1/snapshot")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "proxy_error", "message": f"Could not reach engine {engine_id!r}: {exc}"},
        ) from exc


# ---------------------------------------------------------------------------
# Proxy: submit task to specific engine
# ---------------------------------------------------------------------------


@router.post(
    "/{engine_id}/tasks/run",
    summary="Run a task on a specific engine",
    response_model=dict,
    responses={
        200: {"description": "Task result from the remote node"},
        404: {"description": "Node not registered"},
        502: {"description": "Could not reach the remote node"},
    },
)
def run_task_on_engine(
    engine_id: str,
    body: SubmitToEngineRequest,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Submit and run a task on a specific named engine node.

    The task is proxied to the remote node's ``POST /v1/tasks/run`` endpoint.
    Use this when you need precise control over which node executes the task
    (e.g. GPU-specific work, region affinity).
    """
    node = _get_node_or_404(registry, engine_id)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(
                f"{node.base_url}/v1/tasks/run",
                json=body.model_dump(exclude={"engine_tags"}),
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "proxy_error", "message": f"Could not reach engine {engine_id!r}: {exc}"},
        ) from exc


# ---------------------------------------------------------------------------
# Auto-route: select best engine and run task
# ---------------------------------------------------------------------------


@router.post(
    "/tasks/run",
    summary="Run a task on the best available engine",
    response_model=dict,
    responses={
        200: {"description": "Task result from the selected node"},
        400: {"description": "No healthy engines match the requested tags"},
        502: {"description": "Selected engine is unreachable"},
    },
)
def run_task_auto_route(
    body: SubmitToEngineRequest,
    registry: Annotated[EngineRegistry, Depends(get_cluster_registry)],
):
    """Submit a task to the best available engine node.

    The coordinator selects the most recently active healthy node that
    satisfies all ``engine_tags`` constraints.  This is the primary entry
    point for multi-engine workload distribution.

    Example request:
    ```json
    {
      "name": "ML inference",
      "capability": "infer",
      "input": {"model": "llama3", "prompt": "..."},
      "engine_tags": {"pool": "gpu"}
    }
    ```
    """
    candidates = registry.select(tags=body.engine_tags if body.engine_tags else None)
    if not candidates:
        tag_desc = f" matching tags {body.engine_tags!r}" if body.engine_tags else ""
        raise HTTPException(
            status_code=400,
            detail={
                "code": "no_available_engines",
                "message": f"No healthy engine nodes available{tag_desc}",
            },
        )

    node = candidates[0]  # most recently active
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(
                f"{node.base_url}/v1/tasks/run",
                json=body.model_dump(exclude={"engine_tags"}),
            )
            response.raise_for_status()
            result = response.json()
            # Annotate with routing metadata so the caller knows which node ran it
            if isinstance(result, dict):
                result.setdefault("metadata", {})["routed_to"] = {
                    "engine_id": node.engine_id,
                    "name": node.name,
                    "base_url": node.base_url,
                }
            return result
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "proxy_error",
                "message": f"Engine {node.engine_id!r} ({node.name}) is unreachable: {exc}",
            },
        ) from exc
