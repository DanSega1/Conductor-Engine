"""API-layer request and response models.

These are the public contract shapes for the HTTP API — kept separate from
the internal engine interfaces so the API boundary is explicit and stable.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class APIError(BaseModel):
    """Standard error envelope returned on 4xx / 5xx responses."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable description")
    detail: dict[str, Any] | None = Field(default=None, description="Additional context")


class PageMeta(BaseModel):
    """Pagination metadata included in list responses."""

    limit: int | None = Field(description="Maximum items per page (null = unlimited)")
    offset: int = Field(description="Number of items skipped")
    total: int = Field(description="Total items matching the query")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class SubmitTaskRequest(BaseModel):
    """Submit a new task for execution.

    The task is created in PENDING state and enqueued.  Use the
    ``POST /v1/tasks/run`` endpoint to submit and execute inline.
    """

    name: str = Field(description="Human-readable task name")
    capability: str = Field(description="Registered capability identifier")
    input: dict[str, Any] = Field(default_factory=dict, description="Capability-specific input payload")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary caller metadata")
    max_retries: int = Field(default=0, ge=0, description="Maximum retry attempts on failure")
    workflow_id: str | None = Field(default=None, description="Associate task with a workflow")


class ApproveTaskRequest(BaseModel):
    """Approve a task that is awaiting human or policy approval."""

    actor: str = Field(default="api", description="Identity of the approving actor")
    run: bool = Field(default=True, description="Execute the task immediately after approval")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Approval metadata")


class CancelTaskRequest(BaseModel):
    """Cancel a task that is awaiting approval."""

    actor: str = Field(default="api", description="Identity of the cancelling actor")
    reason: str | None = Field(default=None, description="Cancellation reason recorded in the audit trail")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cluster / multi-engine fleet
# ---------------------------------------------------------------------------


class RegisterEngineRequest(BaseModel):
    """Register a remote Conductor Engine node with this instance.

    Used by wrapper services or node-pool managers to announce that a new
    engine is available.  The ``tags`` dict supports arbitrary labels such
    as ``{"pool": "gpu", "region": "us-east-1", "nodepool": "high-memory"}``.
    """

    name: str = Field(description="Human-readable node name")
    base_url: str = Field(
        description="Base HTTP URL of the remote engine API (e.g. http://10.0.0.5:8080)"
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key/value labels for routing and filtering",
    )


class EngineNodeResponse(BaseModel):
    """Public representation of a registered engine node."""

    engine_id: str
    name: str
    base_url: str
    tags: dict[str, str]
    registered_at: str  # ISO-8601
    last_seen: str       # ISO-8601
    healthy: bool


class EngineListResponse(BaseModel):
    """Paginated list of registered engine nodes."""

    items: list[EngineNodeResponse]
    total: int


class SubmitToEngineRequest(SubmitTaskRequest):
    """Submit a task to a specific (or auto-selected) engine node.

    Inherits all fields from ``SubmitTaskRequest`` and adds optional
    routing hints for multi-engine deployments.
    """

    engine_tags: dict[str, str] = Field(
        default_factory=dict,
        description="Tag constraints for engine selection (e.g. {\"pool\": \"gpu\"})",
    )
