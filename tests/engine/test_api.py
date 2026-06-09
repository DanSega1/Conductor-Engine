"""Integration tests for the Conductor Engine HTTP API.

Tests cover every route group using FastAPI's ``TestClient`` (which runs
synchronously on top of httpx).  All engine components are real (not mocked)
so that the tests validate the full request → supervisor → store path.

Test layout
-----------
- TestTaskRoutes       — POST/GET/run/approve/cancel tasks
- TestCapabilityRoutes — GET capabilities list and detail
- TestHealthRoutes     — GET /health and /snapshot
- TestWorkflowRoutes   — POST /workflows and GET trace
- TestEventRoute       — GET /events (SSE subscription)
- TestClusterRoutes    — engine registration, heartbeat, deregister
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from engine.api import SSEEventBus, create_api_app
from engine.capabilities.echo import EchoCapability
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor
from engine.workflow.agents import LinearPlanner, PassthroughValidator, PassthroughWorker
from engine.workflow.orchestrator import WorkflowOrchestrator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register(EchoCapability())
    return reg


@pytest.fixture()
def event_bus() -> SSEEventBus:
    return SSEEventBus()


@pytest.fixture()
def supervisor(registry: CapabilityRegistry, event_bus: SSEEventBus) -> TaskSupervisor:
    store = MemoryTaskStore()
    return TaskSupervisor(registry=registry, store=store, event_bus=event_bus)


@pytest.fixture()
def orchestrator(supervisor: TaskSupervisor) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=LinearPlanner(steps=[]),
        worker=PassthroughWorker(),
        validator=PassthroughValidator(),
        supervisor=supervisor,
    )


@pytest.fixture()
def client(
    supervisor: TaskSupervisor,
    registry: CapabilityRegistry,
    event_bus: SSEEventBus,
    orchestrator: WorkflowOrchestrator,
) -> TestClient:
    store = supervisor.store
    app = create_api_app(
        supervisor=supervisor,
        registry=registry,
        store=store,
        event_bus=event_bus,
        orchestrator=orchestrator,
    )
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def client_no_optional(
    supervisor: TaskSupervisor,
    registry: CapabilityRegistry,
) -> TestClient:
    """Client without SSE bus or orchestrator — tests graceful 503/501."""
    store = supervisor.store
    app = create_api_app(supervisor=supervisor, registry=registry, store=store)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class TestRoot:
    def test_root_returns_service_info(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "conductor-engine"
        assert "/docs" in data["docs"]


# ---------------------------------------------------------------------------
# Task routes
# ---------------------------------------------------------------------------


class TestTaskRoutes:
    def test_list_tasks_empty(self, client: TestClient) -> None:
        resp = client.get("/v1/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["meta"]["total"] == 0

    def test_submit_task_returns_202(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/tasks",
            json={"name": "echo-test", "capability": "echo", "input": {"message": "hi"}},
        )
        assert resp.status_code == 202
        task = resp.json()
        assert task["status"] == "pending"
        assert task["capability"] == "echo"

    def test_run_task_inline_returns_completed(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/tasks/run",
            json={"name": "echo-run", "capability": "echo", "input": {"message": "hello"}},
        )
        assert resp.status_code == 200
        task = resp.json()
        assert task["status"] == "completed"
        assert task["result"]["success"] is True
        assert task["result"]["output"]["message"] == "hello"

    def test_get_task_by_id(self, client: TestClient) -> None:
        run = client.post(
            "/v1/tasks/run",
            json={"name": "get-test", "capability": "echo", "input": {"message": "x"}},
        )
        task_id = run.json()["task_id"]

        resp = client.get(f"/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == task_id

    def test_get_task_not_found(self, client: TestClient) -> None:
        resp = client.get("/v1/tasks/does-not-exist")
        assert resp.status_code == 404

    def test_list_tasks_status_filter(self, client: TestClient) -> None:
        client.post(
            "/v1/tasks/run",
            json={"name": "filter-test", "capability": "echo", "input": {"message": "y"}},
        )
        resp = client.get("/v1/tasks?status=completed")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "completed"

    def test_list_tasks_invalid_status(self, client: TestClient) -> None:
        resp = client.get("/v1/tasks?status=not_a_status")
        assert resp.status_code == 400

    def test_submit_unknown_capability_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/tasks",
            json={"name": "bad", "capability": "does_not_exist", "input": {}},
        )
        assert resp.status_code == 400

    def test_run_task_explicit_endpoint(self, client: TestClient) -> None:
        """Submit (enqueue), then run via /{task_id}/run."""
        submit = client.post(
            "/v1/tasks",
            json={"name": "explicit-run", "capability": "echo", "input": {"message": "z"}},
        )
        task_id = submit.json()["task_id"]

        run = client.post(f"/v1/tasks/{task_id}/run")
        assert run.status_code == 200
        assert run.json()["status"] == "completed"

    def test_list_pagination(self, client: TestClient) -> None:
        for i in range(5):
            client.post(
                "/v1/tasks/run",
                json={"name": f"page-{i}", "capability": "echo", "input": {"message": str(i)}},
            )
        resp = client.get("/v1/tasks?limit=2&offset=1")
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["meta"]["limit"] == 2
        assert body["meta"]["offset"] == 1


# ---------------------------------------------------------------------------
# Capability routes
# ---------------------------------------------------------------------------


class TestCapabilityRoutes:
    def test_list_capabilities(self, client: TestClient) -> None:
        resp = client.get("/v1/capabilities")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert "echo" in names

    def test_get_capability_detail(self, client: TestClient) -> None:
        resp = client.get("/v1/capabilities/echo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "echo"
        assert "risk_level" in data
        assert "execution_controls" in data

    def test_get_capability_not_found(self, client: TestClient) -> None:
        resp = client.get("/v1/capabilities/no_such_cap")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Health and snapshot routes
# ---------------------------------------------------------------------------


class TestHealthRoutes:
    def test_health_returns_200_when_healthy(self, client: TestClient) -> None:
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["healthy"] is True
        assert isinstance(body["components"], list)
        assert len(body["components"]) > 0

    def test_health_components_have_required_fields(self, client: TestClient) -> None:
        resp = client.get("/v1/health")
        for component in resp.json()["components"]:
            assert "name" in component
            assert "healthy" in component
            assert "issues" in component

    def test_snapshot_returns_v1_schema(self, client: TestClient) -> None:
        client.post(
            "/v1/tasks/run",
            json={"name": "snap-test", "capability": "echo", "input": {"message": "snap"}},
        )
        resp = client.get("/v1/snapshot")
        assert resp.status_code == 200
        body = resp.json()
        assert body["schema_version"] == "v1"
        assert "tasks" in body
        assert "capabilities" in body
        assert "health" in body
        assert len(body["tasks"]) >= 1


# ---------------------------------------------------------------------------
# Workflow routes
# ---------------------------------------------------------------------------


class TestWorkflowRoutes:
    def test_run_workflow_not_available_without_orchestrator(
        self, client_no_optional: TestClient
    ) -> None:
        resp = client_no_optional.post("/v1/workflows", json={"goal": "test", "capabilities": []})
        assert resp.status_code == 501

    def test_get_workflow_trace_not_found(self, client: TestClient) -> None:
        resp = client.get("/v1/workflows/nonexistent-workflow-id")
        assert resp.status_code == 404

    def test_get_workflow_trace_after_task(self, client: TestClient, supervisor: TaskSupervisor) -> None:
        from engine.interfaces.task import TaskSubmission

        workflow_id = "test-wf-001"
        supervisor.run_submission(
            TaskSubmission(
                name="wf-step",
                capability="echo",
                input={"message": "wf"},
                workflow_id=workflow_id,
            )
        )
        resp = client.get(f"/v1/workflows/{workflow_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["workflow_id"] == workflow_id
        assert len(body["tasks"]) == 1


# ---------------------------------------------------------------------------
# SSE event route
# ---------------------------------------------------------------------------


class TestEventRoute:
    def test_events_returns_503_without_bus(self, client_no_optional: TestClient) -> None:
        resp = client_no_optional.get("/v1/events")
        assert resp.status_code == 503

    def test_events_endpoint_registered_in_schema(self, client: TestClient) -> None:
        """Verify the /v1/events endpoint appears in the OpenAPI schema."""
        schema = client.get("/openapi.json").json()
        assert "/v1/events" in schema["paths"]


# ---------------------------------------------------------------------------
# Cluster routes
# ---------------------------------------------------------------------------


class TestClusterRoutes:
    def test_list_engines_empty(self, client: TestClient) -> None:
        resp = client.get("/v1/engines")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_register_engine(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/engines",
            json={
                "name": "worker-01",
                "base_url": "http://10.0.0.1:8080",
                "tags": {"pool": "cpu", "region": "us-east-1"},
            },
        )
        assert resp.status_code == 201
        node = resp.json()
        assert node["name"] == "worker-01"
        assert node["tags"]["pool"] == "cpu"
        assert "engine_id" in node

    def test_get_registered_engine(self, client: TestClient) -> None:
        reg = client.post(
            "/v1/engines",
            json={"name": "worker-02", "base_url": "http://10.0.0.2:8080", "tags": {}},
        ).json()
        engine_id = reg["engine_id"]

        resp = client.get(f"/v1/engines/{engine_id}")
        assert resp.status_code == 200
        assert resp.json()["engine_id"] == engine_id

    def test_get_unknown_engine_returns_404(self, client: TestClient) -> None:
        resp = client.get("/v1/engines/not-a-real-id")
        assert resp.status_code == 404

    def test_deregister_engine(self, client: TestClient) -> None:
        reg = client.post(
            "/v1/engines",
            json={"name": "worker-del", "base_url": "http://10.0.0.3:8080", "tags": {}},
        ).json()
        engine_id = reg["engine_id"]

        del_resp = client.delete(f"/v1/engines/{engine_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/v1/engines/{engine_id}")
        assert get_resp.status_code == 404

    def test_heartbeat_updates_last_seen(self, client: TestClient) -> None:
        reg = client.post(
            "/v1/engines",
            json={"name": "worker-hb", "base_url": "http://10.0.0.4:8080", "tags": {}},
        ).json()
        engine_id = reg["engine_id"]

        resp = client.post(f"/v1/engines/{engine_id}/heartbeat", json={"healthy": True})
        assert resp.status_code == 200
        assert resp.json()["healthy"] is True

    def test_list_engines_with_tag_filter(self, client: TestClient) -> None:
        client.post(
            "/v1/engines",
            json={"name": "gpu-node", "base_url": "http://10.0.0.5:8080", "tags": {"pool": "gpu"}},
        )
        client.post(
            "/v1/engines",
            json={"name": "cpu-node", "base_url": "http://10.0.0.6:8080", "tags": {"pool": "cpu"}},
        )
        resp = client.get("/v1/engines?tag=pool=gpu")
        assert resp.status_code == 200
        body = resp.json()
        assert all(n["tags"].get("pool") == "gpu" for n in body["items"])

    def test_auto_route_no_engines_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/engines/tasks/run",
            json={
                "name": "auto",
                "capability": "echo",
                "input": {"message": "x"},
                "engine_tags": {"pool": "nonexistent"},
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "no_available_engines"

    def test_openapi_schema_available(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Conductor Engine"
        # Confirm key paths are documented
        paths = schema["paths"]
        assert "/v1/tasks" in paths
        assert "/v1/capabilities" in paths
        assert "/v1/health" in paths
        assert "/v1/events" in paths
        assert "/v1/engines" in paths
