"""Webhook trigger ingress routes.

Endpoints
---------
POST  /v1/triggers/{trigger_name}   Deliver a webhook payload to a named adapter
GET   /v1/triggers                  List registered adapters and their health status

The transport layer (this module) is deliberately thin.  All routing logic
lives in ``WebhookIngressService``; the scheduler loop is the consumer.

Usage example
-------------
Register a named webhook adapter when building the scheduler service, then
pass that service to ``create_api_app`` via ``trigger_service``:

    from engine.runtime.scheduler import WebhookIngressService, WebhookTriggerAdapter
    from engine.interfaces.task import TaskSubmission

    adapter = WebhookTriggerAdapter(
        name="github-push",
        mapper=lambda p: TaskSubmission(
            name="on-push",
            capability="echo",
            input={"payload": p},
        ),
    )
    ingress = WebhookIngressService(adapters=[adapter])
    app = create_api_app(..., trigger_service=ingress)

    # Then from any HTTP client:
    POST /v1/triggers/github-push   {"ref": "refs/heads/main", ...}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from engine.api.dependencies import get_trigger_service

router = APIRouter(prefix="/triggers", tags=["triggers"])


def _get_service_or_503(request: Request):
    service = get_trigger_service(request)
    if service is None:
        return None
    return service


@router.post(
    "/{trigger_name}",
    status_code=202,
    summary="Deliver a webhook payload",
    responses={
        202: {"description": "Payload accepted and queued for the next scheduler cycle"},
        404: {"description": "No adapter registered for this trigger name"},
        503: {"description": "Trigger service not configured on this server"},
    },
)
async def ingest_webhook(
    trigger_name: str,
    request: Request,
) -> JSONResponse:
    """Deliver a raw JSON webhook payload to the named trigger adapter.

    The payload is enqueued immediately and submitted to the supervisor on
    the next ``TriggerSchedulerService.run_once()`` cycle.

    **Example (GitHub push webhook):**
    ```bash
    curl -X POST http://localhost:8080/v1/triggers/github-push \\
         -H "Content-Type: application/json" \\
         -d '{"ref": "refs/heads/main", "repository": {"full_name": "org/repo"}}'
    ```

    **Response:**
    ```json
    {"accepted": true, "trigger_name": "github-push", "received_at": "2026-06-09T..."}
    ```
    """
    service = _get_service_or_503(request)
    if service is None:
        return JSONResponse(
            status_code=503,
            content={
                "code": "trigger_service_unavailable",
                "message": "Trigger service is not configured on this server instance",
            },
        )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    received_at = datetime.now(tz=UTC)

    try:
        service.ingest(
            trigger_name=trigger_name,
            payload=payload,
            received_at=received_at,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={"code": "unknown_trigger", "message": str(exc)},
        )

    return JSONResponse(
        status_code=202,
        content={
            "accepted": True,
            "trigger_name": trigger_name,
            "received_at": received_at.isoformat(),
        },
    )


@router.get(
    "",
    summary="List registered trigger adapters",
    responses={
        200: {"description": "Adapter list with health status"},
        503: {"description": "Trigger service not configured on this server"},
    },
)
def list_triggers(request: Request) -> JSONResponse:
    """Return all registered webhook trigger adapters and their health status.

    **Example response:**
    ```json
    [
      {"name": "github-push", "healthy": true, "issues": []},
      {"name": "ci-completed", "healthy": true, "issues": []}
    ]
    ```
    """
    service = _get_service_or_503(request)
    if service is None:
        return JSONResponse(
            status_code=503,
            content={
                "code": "trigger_service_unavailable",
                "message": "Trigger service is not configured on this server instance",
            },
        )

    items = []
    for adapter in service._adapters_by_name.values():
        issues = []
        try:
            issues = list(adapter.health_check())
        except Exception as exc:
            issues = [f"health_check failed: {exc}"]
        items.append(
            {
                "name": adapter.name,
                "healthy": len(issues) == 0,
                "issues": issues,
            }
        )

    return JSONResponse(status_code=200, content=items)
