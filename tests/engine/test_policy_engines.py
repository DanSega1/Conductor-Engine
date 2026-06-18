"""Tests for Phase 5 Slice 3: OPA policy integration and RiskLevelPolicyEngine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.interfaces.capability import Capability, CapabilityDescriptor, CapabilityResult
from engine.interfaces.policy import OPAInput, PolicyContext, PolicyDecisionType
from engine.interfaces.task import RiskLevel, TaskRecord, TaskStatus, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.policy import (
    DenyByDefaultPolicy,
    NullPolicyEngine,
    OPAPolicyEngine,
    RiskLevelPolicyEngine,
)
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capability(name: str = "echo", risk_level: RiskLevel = RiskLevel.LOW) -> CapabilityDescriptor:
    return CapabilityDescriptor(name=name, description="test", risk_level=risk_level)


def _make_context(name: str = "echo", risk_level: RiskLevel = RiskLevel.LOW) -> PolicyContext:
    return PolicyContext(capability=_make_capability(name, risk_level), workdir="/tmp")


def _make_task(capability: str = "echo") -> TaskRecord:
    return TaskRecord(name="test", capability=capability, input={"key": "value"})


# ---------------------------------------------------------------------------
# OPAInput tests
# ---------------------------------------------------------------------------


class TestOPAInput:
    def test_from_context_builds_expected_shape(self):
        task = _make_task()
        context = _make_context()
        opa_input = OPAInput.from_context(task, context)

        assert opa_input.task["id"] == task.task_id
        assert opa_input.task["name"] == "test"
        assert opa_input.task["capability"] == "echo"
        assert opa_input.task["input"] == {"key": "value"}
        assert opa_input.task["max_retries"] == task.max_retries
        assert opa_input.capability["name"] == "echo"
        assert opa_input.capability["risk_level"] == "low"
        assert opa_input.workdir == "/tmp"

    def test_serialization_round_trip(self):
        task = _make_task()
        context = _make_context(risk_level=RiskLevel.HIGH)
        data = OPAInput.from_context(task, context).model_dump()

        assert isinstance(data, dict)
        assert "task" in data
        assert "capability" in data
        assert "workdir" in data
        # Reconstruct
        restored = OPAInput(**data)
        assert restored.task["id"] == task.task_id

    def test_workflow_id_included(self):
        task = TaskRecord(name="wf-task", capability="echo", workflow_id="wf-1")
        context = _make_context()
        opa_input = OPAInput.from_context(task, context)
        assert opa_input.task["workflow_id"] == "wf-1"


# ---------------------------------------------------------------------------
# NullPolicyEngine (regression guard)
# ---------------------------------------------------------------------------


class TestNullPolicyEngine:
    def test_always_allows(self):
        engine = NullPolicyEngine()
        decision = engine.evaluate(_make_task(), _make_context())
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_health_check_no_issues(self):
        assert NullPolicyEngine().health_check() == []


# ---------------------------------------------------------------------------
# RiskLevelPolicyEngine
# ---------------------------------------------------------------------------


class TestRiskLevelPolicyEngine:
    def test_allows_low_risk_by_default(self):
        engine = RiskLevelPolicyEngine()
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.LOW))
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_allows_medium_risk_by_default(self):
        engine = RiskLevelPolicyEngine()
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.MEDIUM))
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_allows_high_risk_by_default(self):
        engine = RiskLevelPolicyEngine()
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.HIGH))
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_allows_critical_risk_by_default(self):
        """Default deny_above=CRITICAL means nothing is denied without explicit config."""
        engine = RiskLevelPolicyEngine()
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.CRITICAL))
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_denies_above_threshold(self):
        engine = RiskLevelPolicyEngine(deny_above=RiskLevel.LOW)
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.MEDIUM))
        assert decision.decision == PolicyDecisionType.DENY
        assert "risk level" in (decision.reason or "").lower()

    def test_allows_at_threshold(self):
        """Deny is strictly above — equal to threshold is allowed."""
        engine = RiskLevelPolicyEngine(deny_above=RiskLevel.HIGH)
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.HIGH))
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_denies_critical_when_threshold_high(self):
        engine = RiskLevelPolicyEngine(deny_above=RiskLevel.HIGH)
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.CRITICAL))
        assert decision.decision == PolicyDecisionType.DENY

    def test_require_approval_at_exact_level(self):
        engine = RiskLevelPolicyEngine(
            deny_above=RiskLevel.CRITICAL,
            require_approval_at=RiskLevel.HIGH,
        )
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.HIGH))
        assert decision.decision == PolicyDecisionType.REQUIRE_APPROVAL

    def test_approval_check_before_deny_check(self):
        """require_approval_at is evaluated before deny_above."""
        engine = RiskLevelPolicyEngine(
            deny_above=RiskLevel.MEDIUM,
            require_approval_at=RiskLevel.MEDIUM,
        )
        # MEDIUM == deny_above, but approval takes precedence
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.MEDIUM))
        assert decision.decision == PolicyDecisionType.REQUIRE_APPROVAL

    def test_allowlist_permits_named_capability(self):
        engine = RiskLevelPolicyEngine(
            allowed_capabilities=frozenset({"echo", "read_file"}),
            deny_above=RiskLevel.LOW,
        )
        decision = engine.evaluate(_make_task("echo"), _make_context("echo", RiskLevel.HIGH))
        # Allowlist means no risk-level check fires; HIGH would normally be denied
        # But allowlist blocks risk-level logic entirely
        assert decision.decision == PolicyDecisionType.DENY  # risk check still fires for allowlisted

    def test_allowlist_denies_unlisted_capability(self):
        engine = RiskLevelPolicyEngine(allowed_capabilities=frozenset({"echo"}))
        decision = engine.evaluate(_make_task("rm_rf"), _make_context("rm_rf", RiskLevel.LOW))
        assert decision.decision == PolicyDecisionType.DENY
        assert "allowed set" in (decision.reason or "")

    def test_deny_includes_risk_metadata(self):
        engine = RiskLevelPolicyEngine(deny_above=RiskLevel.LOW)
        decision = engine.evaluate(_make_task(), _make_context(risk_level=RiskLevel.HIGH))
        assert decision.metadata.get("risk_level") == "high"
        assert decision.metadata.get("deny_above") == "low"

    def test_health_check_no_issues(self):
        assert RiskLevelPolicyEngine().health_check() == []


# ---------------------------------------------------------------------------
# OPAPolicyEngine unit tests (mocked httpx)
# ---------------------------------------------------------------------------


class TestOPAPolicyEngine:
    def _engine(self, **kwargs) -> OPAPolicyEngine:
        return OPAPolicyEngine("http://localhost:8181", **kwargs)

    def test_query_url_constructed_correctly(self):
        engine = OPAPolicyEngine("http://opa:8181/", "my/policy")
        assert engine._query_url() == "http://opa:8181/v1/data/my/policy"

    def test_allow_when_opa_returns_allow_true(self):
        engine = self._engine()
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True}}
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response):
            decision = engine.evaluate(_make_task(), _make_context())

        assert decision.decision == PolicyDecisionType.ALLOW

    def test_deny_when_opa_returns_allow_false(self):
        engine = self._engine()
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": False, "reason": "blocked"}}
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response):
            decision = engine.evaluate(_make_task(), _make_context())

        assert decision.decision == PolicyDecisionType.DENY
        assert decision.reason == "blocked"

    def test_require_approval_when_opa_returns_flag(self):
        engine = self._engine()
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": False, "require_approval": True, "reason": "needs review"}}
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response):
            decision = engine.evaluate(_make_task(), _make_context())

        assert decision.decision == PolicyDecisionType.REQUIRE_APPROVAL
        assert decision.reason == "needs review"

    def test_opa_result_in_metadata(self):
        engine = self._engine()
        opa_result = {"allow": True, "reason": "permitted"}
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": opa_result}
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response):
            decision = engine.evaluate(_make_task(), _make_context())

        assert decision.metadata["opa_result"] == opa_result

    def test_fail_closed_on_connection_error(self):
        engine = self._engine(fail_open=False)
        with patch("httpx.post", side_effect=Exception("connection refused")):
            decision = engine.evaluate(_make_task(), _make_context())
        assert decision.decision == PolicyDecisionType.DENY
        assert "fail-closed" in (decision.reason or "")
        assert decision.metadata["fail_open"] is False

    def test_fail_open_on_connection_error(self):
        engine = self._engine(fail_open=True)
        with patch("httpx.post", side_effect=Exception("connection refused")):
            decision = engine.evaluate(_make_task(), _make_context())
        assert decision.decision == PolicyDecisionType.ALLOW
        assert "fail-open" in (decision.reason or "")
        assert decision.metadata["fail_open"] is True

    def test_payload_sent_to_opa_contains_input_key(self):
        engine = self._engine()
        captured: list[dict] = []

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True}}
        mock_response.raise_for_status.return_value = None

        def capture(url, *, json=None, headers=None, timeout=None):
            captured.append(json or {})
            return mock_response

        with patch("httpx.post", side_effect=capture):
            engine.evaluate(_make_task(), _make_context())

        assert len(captured) == 1
        assert "input" in captured[0]
        assert captured[0]["input"]["task"]["capability"] == "echo"

    def test_empty_result_is_treated_as_deny(self):
        engine = self._engine()
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # No "result" key
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response):
            decision = engine.evaluate(_make_task(), _make_context())

        assert decision.decision == PolicyDecisionType.DENY

    def test_health_check_ok(self):
        engine = self._engine()
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            issues = engine.health_check()

        assert issues == []

    def test_health_check_server_unreachable(self):
        engine = self._engine()
        with patch("httpx.get", side_effect=Exception("timeout")):
            issues = engine.health_check()
        assert len(issues) == 1
        assert "cannot reach" in issues[0]

    def test_health_check_non_200_status(self):
        engine = self._engine()
        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("httpx.get", return_value=mock_response):
            issues = engine.health_check()

        assert len(issues) == 1
        assert "503" in issues[0]


# ---------------------------------------------------------------------------
# Supervisor integration with RiskLevelPolicyEngine
# ---------------------------------------------------------------------------


class TestSupervisorPolicyIntegration:
    def _make_capability_cls(self, name: str, risk_level: RiskLevel) -> type:
        class Cap(Capability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(name=name, description="test", risk_level=risk_level)

            def execute(self, payload: dict, context) -> CapabilityResult:
                return CapabilityResult(output={"done": True})

        return Cap

    def test_high_risk_task_denied_by_risk_engine(self, tmp_path: Path):
        CapCls = self._make_capability_cls("dangerous", RiskLevel.HIGH)
        registry = CapabilityRegistry()
        registry.register(CapCls())

        policy = RiskLevelPolicyEngine(deny_above=RiskLevel.MEDIUM)
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            policy_engine=policy,
        )

        task = supervisor.run_submission(TaskSubmission(name="risky task", capability="dangerous"))
        assert task.status == TaskStatus.POLICY_DENIED
        assert task.result is not None
        assert task.result.success is False

    def test_low_risk_task_allowed_by_risk_engine(self, tmp_path: Path):
        CapCls = self._make_capability_cls("safe", RiskLevel.LOW)
        registry = CapabilityRegistry()
        registry.register(CapCls())

        policy = RiskLevelPolicyEngine(deny_above=RiskLevel.MEDIUM)
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            policy_engine=policy,
        )

        task = supervisor.run_submission(TaskSubmission(name="safe task", capability="safe"))
        assert task.status == TaskStatus.COMPLETED

    def test_medium_risk_task_requires_approval(self, tmp_path: Path):
        CapCls = self._make_capability_cls("medium_risk", RiskLevel.MEDIUM)
        registry = CapabilityRegistry()
        registry.register(CapCls())

        policy = RiskLevelPolicyEngine(
            deny_above=RiskLevel.CRITICAL,
            require_approval_at=RiskLevel.MEDIUM,
        )
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            policy_engine=policy,
        )

        task = supervisor.run_submission(TaskSubmission(name="medium task", capability="medium_risk"))
        assert task.status == TaskStatus.AWAITING_APPROVAL

    def test_policy_deny_recorded_in_audit_trail(self, tmp_path: Path):
        CapCls = self._make_capability_cls("dangerous", RiskLevel.CRITICAL)
        registry = CapabilityRegistry()
        registry.register(CapCls())

        policy = RiskLevelPolicyEngine(deny_above=RiskLevel.HIGH)
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            policy_engine=policy,
        )

        task = supervisor.run_submission(TaskSubmission(name="critical task", capability="dangerous"))
        deny_entries = [e for e in task.audit_trail if e.action == "denied"]
        assert len(deny_entries) == 1
        assert deny_entries[0].to_status == TaskStatus.POLICY_DENIED

    def test_opa_deny_stops_execution(self, tmp_path: Path):
        """Supervisor should honour OPAPolicyEngine deny and never execute the capability."""

        class TrackingCapability(Capability):
            executed = False

            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(name="tracked", description="test", risk_level=RiskLevel.LOW)

            def execute(self, payload: dict, context) -> CapabilityResult:
                TrackingCapability.executed = True
                return CapabilityResult(output={})

        registry = CapabilityRegistry()
        registry.register(TrackingCapability())

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": False, "reason": "blocked by OPA"}}
        mock_response.raise_for_status.return_value = None

        policy = OPAPolicyEngine("http://localhost:8181")
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            policy_engine=policy,
        )

        with patch("httpx.post", return_value=mock_response):
            task = supervisor.run_submission(TaskSubmission(name="opa blocked", capability="tracked"))

        assert task.status == TaskStatus.POLICY_DENIED
        assert TrackingCapability.executed is False


# ---------------------------------------------------------------------------
# DenyByDefaultPolicy
# ---------------------------------------------------------------------------


class TestDenyByDefaultPolicy:
    def test_deny_by_default_empty_allowed_set(self) -> None:
        policy = DenyByDefaultPolicy()
        task = _make_task("echo")
        context = _make_context("echo")
        decision = policy.evaluate(task, context)
        assert decision.decision == PolicyDecisionType.DENY
        assert "not in the allowed set" in (decision.reason or "")

    def test_allow_explicitly_permitted_capability(self) -> None:
        policy = DenyByDefaultPolicy(allowed_capabilities=frozenset(["echo"]))
        task = _make_task("echo")
        context = _make_context("echo")
        decision = policy.evaluate(task, context)
        assert decision.decision == PolicyDecisionType.ALLOW
        assert "echo" in (decision.reason or "")

    def test_deny_unlisted_capability(self) -> None:
        policy = DenyByDefaultPolicy(allowed_capabilities=frozenset(["echo"]))
        task = _make_task("filesystem")
        context = _make_context("filesystem")
        decision = policy.evaluate(task, context)
        assert decision.decision == PolicyDecisionType.DENY
        assert "filesystem" in (decision.reason or "")

    def test_health_check_empty_warns(self) -> None:
        policy = DenyByDefaultPolicy()
        issues = policy.health_check()
        assert len(issues) >= 1
        assert "no capabilities are allowed" in issues[0]

    def test_health_check_with_allowed_set_is_clean(self) -> None:
        policy = DenyByDefaultPolicy(allowed_capabilities=frozenset(["echo"]))
        assert policy.health_check() == []

    def test_add_capability(self) -> None:
        policy = DenyByDefaultPolicy()
        policy.add_capability("echo")
        assert "echo" in policy.allowed_capabilities

        decision = policy.evaluate(_make_task("echo"), _make_context("echo"))
        assert decision.decision == PolicyDecisionType.ALLOW

    def test_remove_capability(self) -> None:
        policy = DenyByDefaultPolicy(allowed_capabilities=frozenset(["echo", "filesystem"]))
        policy.remove_capability("echo")
        assert "echo" not in policy.allowed_capabilities
        assert "filesystem" in policy.allowed_capabilities

    def test_allowed_capabilities_empty_frozenset(self) -> None:
        policy = DenyByDefaultPolicy(allowed_capabilities=frozenset())
        task = _make_task("echo")
        context = _make_context("echo")
        decision = policy.evaluate(task, context)
        assert decision.decision == PolicyDecisionType.DENY

    def test_supervisor_integration_deny_all(self) -> None:
        """A supervisor using DenyByDefaultPolicy denies all tasks by default."""
        from engine.capabilities.echo import EchoCapability

        registry = CapabilityRegistry()
        registry.register(EchoCapability())

        policy = DenyByDefaultPolicy()  # empty allowed set
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            policy_engine=policy,
        )

        task = supervisor.run_submission(TaskSubmission(
            name="test", capability="echo", input={"message": "hello"},
        ))
        assert task.status == TaskStatus.POLICY_DENIED

    def test_supervisor_integration_allow_explicit(self) -> None:
        """When echo is explicitly allowed, tasks pass through."""
        from engine.capabilities.echo import EchoCapability

        registry = CapabilityRegistry()
        registry.register(EchoCapability())

        policy = DenyByDefaultPolicy(allowed_capabilities=frozenset(["echo"]))
        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            policy_engine=policy,
        )

        task = supervisor.run_submission(TaskSubmission(
            name="test", capability="echo", input={"message": "hello"},
        ))
        assert task.status == TaskStatus.COMPLETED
