"""Capability registry browser routes.

Endpoints
---------
GET  /v1/capabilities            List all registered capabilities
GET  /v1/capabilities/{name}     Get a single capability by name
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.api.dependencies import RegistryDep
from engine.control_plane.contracts import ControlPlaneCapabilityV1

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get(
    "",
    summary="List capabilities",
    response_model=list,
    responses={200: {"description": "All registered capabilities"}},
)
def list_capabilities(registry: RegistryDep):
    """Return every capability loaded in the current engine instance.

    Each entry includes the name, description, risk level, tags, and
    runtime execution controls (timeout, rate limit).

    Example response:
    ```json
    [
      {
        "name": "echo",
        "description": "Echo the input message back as output.",
        "risk_level": "low",
        "tags": ["builtin"],
        "execution_controls": {"timeout_seconds": null, "min_interval_seconds": null}
      }
    ]
    ```
    """
    return [
        ControlPlaneCapabilityV1.from_descriptor(
            descriptor,
            registry.execution_controls(descriptor.name),
        ).model_dump()
        for descriptor in registry.list()
    ]


@router.get(
    "/{name}",
    summary="Get a capability",
    response_model=dict,
    responses={
        200: {"description": "Capability detail"},
        404: {"description": "Capability not found"},
    },
)
def get_capability(name: str, registry: RegistryDep):
    """Return detail for a single capability by name."""
    try:
        capability = registry.get(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Capability {name!r} not found"},
        ) from exc
    descriptor = capability.descriptor
    controls = registry.execution_controls(name)
    return ControlPlaneCapabilityV1.from_descriptor(descriptor, controls).model_dump()
