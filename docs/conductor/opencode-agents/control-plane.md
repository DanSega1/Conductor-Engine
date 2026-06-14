# Control Plane Agent

**Config:** `.opencode/agents/control-plane/control-plane.json`
**Engine ref:** `engine/api/`
**Priority:** 10
**Role:** Versioned HTTP FastAPI control-plane API surfaced by `cond serve`.

## Purpose

The control plane agent exposes the engine's functionality over HTTP: task CRUD, capability browsing, workflow submission, SSE event streams, health/snapshot endpoints, and multi-engine cluster routing. It is consumed by `condor-tui`, SDK clients, and future web UIs. It wraps the supervisor, registry, store, and event bus — it does not replace them.

## Invariants

- Wires the engine stack (`create_api_app()`) — does not duplicate engine logic.
- Auth context is a placeholder (`AuthContext` + `get_auth_context`) — Phase 7 replaces the implementation without touching route handlers.
- Returns versioned read models from `engine/control_plane/contracts.py` (ControlPlaneTaskV1, ControlPlaneSnapshotV1, etc.).
- Multi-engine cluster routes proxy to remote nodes via httpx.

## Endpoints

| Group | Prefix | Methods | Purpose |
|---|---|---|---|
| Tasks | `/v1/tasks` | GET, POST | List, submit, run inline, approve, cancel |
| Capabilities | `/v1/capabilities` | GET | Registry browser |
| Workflows | `/v1/workflows` | POST, GET | Submit and trace workflow execution |
| Events | `/v1/events` | GET (SSE) | Server-Sent Events stream with type filter |
| Health | `/v1/health` | GET | Component health; 503 on issues |
| Snapshot | `/v1/snapshot` | GET | Full `ControlPlaneSnapshotV1` |
| Triggers | `/v1/triggers` | POST, GET | Webhook ingress, trigger listing |
| Engines | `/v1/engines` | GET, POST | Multi-engine cluster: register, heartbeat, route |
| Engines Tasks | `/v1/engines/tasks/run` | POST | Tag-based auto-routing to remote nodes |

## SSE stream

```
GET /v1/events                          → all events
GET /v1/events?types=task_completed,task_failed  → filtered
```

## Multi-engine routing

```bash
# Register a node
curl -X POST http://coordinator:8080/v1/engines \
  -H "Content-Type: application/json" \
  -d '{"name": "worker-gpu-01", "base_url": "http://10.0.0.5:8080", "tags": {"pool": "gpu"}}'

# Route task by tag
curl -X POST http://coordinator:8080/v1/engines/tasks/run \
  -H "Content-Type: application/json" \
  -d '{"name": "infer", "capability": "echo", "input": {}, "engine_tags": {"pool": "gpu"}}'
```

## Delegation

```
control-plane
├── supervisor          → run_submission, submit, approve, cancel, list_tasks
├── capability-registry → list_capabilities, get_descriptor
├── event-bus           → SSE stream subscriptions (SSEEventBus)
└── task-store          → read task records for snapshot/listing
```

## When to use

- When the engine needs an HTTP API surface
- For multi-engine fleet orchestration with tag-based routing
- When condor-tui or a web UI consumes the engine
- For SDK clients that interact with Conductor over HTTP
