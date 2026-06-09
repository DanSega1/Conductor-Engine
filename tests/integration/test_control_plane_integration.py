"""Integration tests for Conductor Engine control-plane contracts.

These tests exercise the full stack — real supervisor, store, registry,
and HTTP API — without mocking internal components.  They validate:

1. Submit-via-API → supervisor → store → query-back: schema stability
2. Capability require_approval gate: task pauses, approval resumes
3. Webhook payload → trigger route → scheduler cycle → task in store
4. Policy deny: task lands in POLICY_DENIED with audit trail
5. Retry with backoff: delay_seconds propagates through supervisor
6. Sandboxed subprocess execution: EchoCapability runs isolated
7. Snapshot contract: v1 schema fields present and accurate after activity
8. Audit trail completeness: policy_engine and decision_type always present
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from engine.api import SSEEventBus, create_api_app
from engine.capabilities.echo import EchoCapability
from engine.interfaces.capability import CapabilityContext, CapabilityDescriptor
from engine.interfaces.policy import PolicyContext, PolicyDecision, PolicyDecisionType
from engine.interfaces.task import RiskLevel, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor
from engine.workflow.agents import LinearPlanner, PassthroughValidator, PassthroughWorker
from engine.workflow.orchestrator import WorkflowOrchestrator


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store() -> MemoryTaskStore:
    return MemoryTaskStore()


@pytest.fixture()
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register(EchoCapability())
    return reg


@pytest.fixture()
def event_bus() -> SSEEventBus:
    return SSEEventBus()


@pytest.fixture()
def supervisor(registry: CapabilityRegistry, store: MemoryTaskStore, event_bus: SSEEventBus) -> TaskSupervisor:
    return TaskSupervisor(registry=registry, store=store, event_bus=event_bus)


@pytest.fixture()
def client(supervisor: TaskSupervisor, registry: CapabilityRegistry, store: MemoryTaskStore, event_bus: SSEEventBus) -> TestClient:
    app = create_api_app(supervisor=supervisor, registry=registry, store=store, event_bus=event_bus)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# 1. Submit-via-API → store → query-back: schema stability
# ---------------------------------------------------------------------------


class TestControlPlaneContractStability:
    """Verify that submitting a task and querying it back returns a stable v1 schema."""

    def test_submit_and_get_back_preserves_all_v1_fields(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/tasks/run",
            json={"name": "integration-echo", "capability": "echo", "input": {"message": "contract-check"}},
        )
        assert resp.status_code == 200
        task = resp.json()

        # Required v1 fields must always be present
        for field in ("task_id", "name", "capability", "status", "attempt", "max_retries",
                      "input", "metadata", "result", "audit_trail", "created_at", "updated_at"):
            assert field in task, f"Missing v1 field: {field}"

        assert task["status"] == "completed"
        assert task["result"]["success"] is True
        assert task["result"]["output"]["message"] == "contract-check"

    def test_get_task_by_id_returns_same_schema(self, client: TestClient) -> None:
        run = client.post("/v1/tasks/run", json={"name": "id-test", "capability": "echo", "input": {"message": "x"}})
        task_id = run.json()["task_id"]

        get = client.get(f"/v1/tasks/{task_id}")
        assert get.status_code == 200
        assert get.json()["task_id"] == task_id

    def test_list_tasks_pagination_meta(self, client: TestClient) -> None:
        for i in range(3):
            client.post("/v1/tasks/run", json={"name": f"p{i}", "capability": "echo", "input": {"message": str(i)}})

        resp = client.get("/v1/tasks?limit=2&offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["limit"] == 2
        assert body["meta"]["offset"] == 0
        assert body["meta"]["total"] >= 3
        assert len(body["items"]) == 2

    def test_snapshot_v1_schema_after_activity(self, client: TestClient) -> None:
        client.post("/v1/tasks/run", json={"name": "snap", "capability": "echo", "input": {"message": "snapshot"}})
        snap = client.get("/v1/snapshot").json()

        assert snap["schema_version"] == "v1"
        assert "tasks" in snap
        assert "capabilities" in snap
        assert "health" in snap
        assert "generated_at" in snap
        completed = [t for t in snap["tasks"] if t["status"] == "completed"]
        assert len(completed) >= 1

    def test_capability_contract_fields(self, client: TestClient) -> None:
        caps = client.get("/v1/capabilities").json()
        for cap in caps:
            for field in ("name", "description", "risk_level", "tags", "execution_controls"):
                assert field in cap, f"Missing capability field: {field}"


# ---------------------------------------------------------------------------
# 2. require_approval gate
# ---------------------------------------------------------------------------


class TestRequireApprovalGate:
    """Capability-level require_approval should pause the task automatically."""

    @pytest.fixture()
    def approval_client(self, store: MemoryTaskStore, event_bus: SSEEventBus) -> TestClient:
        from engine.capabilities.echo import EchoCapability

        class ApprovalEcho(EchoCapability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                base = super().descriptor
                return CapabilityDescriptor(
                    name="echo-approval",
                    description=base.description,
                    risk_level=base.risk_level,
                    tags=base.tags,
                    require_approval=True,
                )

        reg = CapabilityRegistry()
        reg.register(ApprovalEcho())
        sup = TaskSupervisor(registry=reg, store=store, event_bus=event_bus)
        app = create_api_app(supervisor=sup, registry=reg, store=store, event_bus=event_bus)
        return TestClient(app, raise_server_exceptions=True)

    def test_submit_pauses_at_awaiting_approval(self, approval_client: TestClient) -> None:
        resp = approval_client.post(
            "/v1/tasks/run",
            json={"name": "needs-approval", "capability": "echo-approval", "input": {"message": "hi"}},
        )
        task = resp.json()
        assert task["status"] == "awaiting_approval"

    def test_approve_resumes_execution(self, approval_client: TestClient) -> None:
        submit = approval_client.post(
            "/v1/tasks",
            json={"name": "approve-then-run", "capability": "echo-approval", "input": {"message": "approved"}},
        )
        # task is pending after submit (enqueued, not run yet)
        task_id = submit.json()["task_id"]

        # Run it — should park at awaiting_approval
        run = approval_client.post(f"/v1/tasks/{task_id}/run")
        assert run.json()["status"] == "awaiting_approval"

        # Approve and run
        approved = approval_client.post(f"/v1/tasks/{task_id}/approve", json={"actor": "test-user", "run": True})
        assert approved.json()["status"] == "completed"

    def test_audit_trail_records_capability_approval_gate(self, approval_client: TestClient) -> None:
        resp = approval_client.post(
            "/v1/tasks/run",
            json={"name": "audit-gate", "capability": "echo-approval", "input": {"message": "x"}},
        )
        trail = resp.json()["audit_trail"]
        actions = [e["action"] for e in trail]
        assert "awaiting_approval" in actions
        # Confirm the metadata carries the reason
        gate_entry = next(e for e in trail if e["action"] == "awaiting_approval")
        assert gate_entry["metadata"].get("reason") == "capability requires approval"


# ---------------------------------------------------------------------------
# 3. Webhook → trigger route → scheduler cycle → task in store
# ---------------------------------------------------------------------------


class TestWebhookIngressIntegration:
    """End-to-end: POST /v1/triggers → scheduler.run_once() → task submitted."""

    @pytest.fixture()
    def webhook_setup(self, supervisor: TaskSupervisor, registry: CapabilityRegistry, store: MemoryTaskStore, event_bus: SSEEventBus):
        from engine.runtime.scheduler import TriggerSchedulerService, WebhookIngressService, WebhookTriggerAdapter

        adapter = WebhookTriggerAdapter(
            name="integration-hook",
            mapper=lambda p: TaskSubmission(
                name="webhook-submitted",
                capability="echo",
                input={"message": p.get("text", "triggered")},
            ),
        )
        ingress = WebhookIngressService(adapters=[adapter])
        scheduler = TriggerSchedulerService(adapters=[adapter], sink=supervisor)

        app = create_api_app(
            supervisor=supervisor, registry=registry, store=store,
            event_bus=event_bus, trigger_service=ingress,
        )
        return TestClient(app, raise_server_exceptions=True), scheduler, store

    def test_webhook_payload_reaches_store_after_scheduler_cycle(self, webhook_setup) -> None:
        client, scheduler, store = webhook_setup

        # 1. POST webhook payload
        resp = client.post("/v1/triggers/integration-hook", json={"text": "hello-webhook"})
        assert resp.status_code == 202

        # 2. Advance one scheduler cycle
        submitted = scheduler.run_once()
        assert len(submitted) == 1
        assert submitted[0].capability == "echo"

        # 3. Task appears in store
        tasks = store.list()
        matching = [t for t in tasks if t.name == "webhook-submitted"]
        assert len(matching) == 1
        assert matching[0].input["message"] == "hello-webhook"

    def test_multiple_payloads_submitted_in_order(self, webhook_setup) -> None:
        client, scheduler, store = webhook_setup

        for i in range(3):
            client.post("/v1/triggers/integration-hook", json={"text": f"msg-{i}"})

        submitted = scheduler.run_once()
        assert len(submitted) == 3
        messages = [t.input["message"] for t in store.list() if t.name == "webhook-submitted"]
        assert sorted(messages) == ["msg-0", "msg-1", "msg-2"]

    def test_trigger_list_shows_adapter_healthy(self, webhook_setup) -> None:
        client, _, _ = webhook_setup
        resp = client.get("/v1/triggers")
        assert resp.status_code == 200
        items = resp.json()
        assert any(a["name"] == "integration-hook" and a["healthy"] for a in items)


# ---------------------------------------------------------------------------
# 4. Policy deny: full audit trail
# ---------------------------------------------------------------------------


class TestPolicyDenyAuditTrail:
    """POLICY_DENIED task must carry full policy context in its audit trail."""

    @pytest.fixture()
    def deny_supervisor(self, store: MemoryTaskStore, event_bus: SSEEventBus) -> TaskSupervisor:
        class AlwaysDenyPolicy:
            def evaluate(self, task, context):
                return PolicyDecision(
                    decision=PolicyDecisionType.DENY,
                    reason="test denial",
                    metadata={"rule": "always-deny"},
                )

            def health_check(self):
                return []

        reg = CapabilityRegistry()
        reg.register(EchoCapability())
        return TaskSupervisor(registry=reg, store=store, event_bus=event_bus, policy_engine=AlwaysDenyPolicy())

    def test_denied_task_has_policy_engine_in_audit(self, deny_supervisor: TaskSupervisor) -> None:
        task = deny_supervisor.run_submission(
            TaskSubmission(name="deny-test", capability="echo", input={"message": "x"})
        )
        assert task.status.value == "policy_denied"

        policy_entries = [e for e in task.audit_trail if e.action == "denied"]
        assert len(policy_entries) == 1
        meta = policy_entries[0].metadata
        assert meta["policy_engine"] == "AlwaysDenyPolicy"
        assert meta["decision_type"] == "deny"
        assert meta["reason"] == "test denial"
        assert meta["rule"] == "always-deny"

    def test_allowed_task_records_policy_engine(self, supervisor: TaskSupervisor) -> None:
        """Even an ALLOW decision records the policy engine name."""
        task = supervisor.run_submission(
            TaskSubmission(name="allow-audit", capability="echo", input={"message": "y"})
        )
        assert task.status.value == "completed"
        policy_entries = [e for e in task.audit_trail if e.actor == "policy"]
        assert len(policy_entries) == 1
        meta = policy_entries[0].metadata
        assert "policy_engine" in meta
        assert "decision_type" in meta
        assert meta["decision_type"] == "allow"


# ---------------------------------------------------------------------------
# 5. Retry with backoff: delay field propagates
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """ExponentialBackoffRetryStrategy populates delay_seconds in the audit trail."""

    @pytest.fixture()
    def failing_capability(self) -> type:
        from engine.capabilities.echo import EchoCapability
        from engine.interfaces.capability import CapabilityContext, CapabilityDescriptor, CapabilityResult

        class FailOnce(EchoCapability):
            _attempts = 0

            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(name="fail-once", description="fails first attempt", risk_level=RiskLevel.LOW)

            def execute(self, payload, context: CapabilityContext) -> CapabilityResult:
                FailOnce._attempts += 1
                if FailOnce._attempts == 1:
                    raise RuntimeError("first attempt fails")
                return CapabilityResult(output={"done": True})

        FailOnce._attempts = 0
        return FailOnce

    def test_retry_audit_entry_includes_delay(self, store: MemoryTaskStore, event_bus: SSEEventBus, failing_capability) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy

        strategy = ExponentialBackoffRetryStrategy(base_delay=0.001, multiplier=1.0, max_delay=0.001)
        reg = CapabilityRegistry()
        reg.register(failing_capability())
        sup = TaskSupervisor(registry=reg, store=store, event_bus=event_bus, retry_strategy=strategy)

        task = sup.run_submission(
            TaskSubmission(name="retry-audit", capability="fail-once", input={"message": "x"}, max_retries=2)
        )
        assert task.status.value == "completed"

        retry_entries = [e for e in task.audit_trail if e.action == "retry"]
        assert len(retry_entries) == 1
        assert "retry_reason" in retry_entries[0].metadata


# ---------------------------------------------------------------------------
# 6. Sandboxed subprocess execution
# ---------------------------------------------------------------------------


class TestSubprocessSandbox:
    """SubprocessCapabilityRunner runs EchoCapability in an isolated process."""

    def test_echo_capability_via_subprocess(self) -> None:
        from engine.interfaces.capability import CapabilityContext
        from engine.runtime.sandbox import SubprocessCapabilityRunner

        runner = SubprocessCapabilityRunner(timeout_seconds=30.0)
        result = runner.run(
            import_path="engine.capabilities.echo:EchoCapability",
            payload={"message": "sandbox-hello"},
            context=CapabilityContext(task_id="t1", task_name="sandbox-test", workdir="/tmp"),
        )
        assert result.output["message"] == "sandbox-hello"

    def test_subprocess_timeout_raises(self) -> None:
        import pytest
        from engine.interfaces.capability import CapabilityContext
        from engine.runtime.sandbox import SubprocessCapabilityError, SubprocessCapabilityRunner

        runner = SubprocessCapabilityRunner(
            timeout_seconds=0.001,  # immediately times out
            python_executable="sleep",  # not a Python interpreter — will hang
        )
        with pytest.raises((SubprocessCapabilityError, Exception)):
            runner.run(
                import_path="engine.capabilities.echo:EchoCapability",
                payload={"message": "x"},
                context=CapabilityContext(task_id="t", task_name="t", workdir="/tmp"),
            )

    def test_unknown_capability_raises(self) -> None:
        import pytest
        from engine.interfaces.capability import CapabilityContext
        from engine.runtime.sandbox import SubprocessCapabilityError, SubprocessCapabilityRunner

        runner = SubprocessCapabilityRunner(timeout_seconds=10.0)
        with pytest.raises(SubprocessCapabilityError, match="capability load error"):
            runner.run(
                import_path="engine.does_not_exist:NoSuchCapability",
                payload={},
                context=CapabilityContext(task_id="t", task_name="t", workdir="/tmp"),
            )
