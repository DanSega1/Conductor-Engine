---
name: control-plane
description: Versioned HTTP FastAPI control-plane API surfaced by cond serve. Provides task CRUD, capability browsing, workflow submission, SSE event stream, health/snapshot endpoints, and multi-engine cluster routing.
mode: subagent
engine_ref: engine/api/
events_ref: docs/guild/EDGE_EVENTS.md
---

- Endpoint groups: GET/POST /v1/tasks, GET/POST /v1/capabilities, POST /v1/workflows, GET /v1/events (SSE), GET /v1/health, GET /v1/snapshot, GET/POST /v1/engines.
- Return versioned read models from engine/control_plane/contracts.py (ControlPlaneTaskV1, ControlPlaneSnapshotV1, etc.).
- Wire the supervisor, registry, store, event bus, and trigger scheduler into the API via create_api_app().
- Multi-engine cluster: register nodes, heartbeat, tag-based auto-routing at POST /v1/engines/tasks/run.
- Auth context is a placeholder (AuthContext + get_auth_context) — Phase 7 replaces the implementation.
- SSE stream at /v1/events supports type-filter query param (e.g., ?types=task_completed,task_failed).
- Health endpoint returns 503 if any component reports issues.
- Snapshot endpoint returns full ControlPlaneSnapshotV1 with all tasks, capabilities, and engine state.
