"""Tests for Phase 5 Slice 2: Escalation Paths."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError
import pytest

from engine.interfaces.capability import Capability, CapabilityDescriptor, CapabilityResult
from engine.interfaces.event import EventType, TaskEvent
from engine.interfaces.retry import FailureContext
from engine.interfaces.task import RiskLevel, TaskRecord, TaskStatus, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor

# === EscalationConfig Tests ===


class TestEscalationConfig:
    """Test EscalationConfig Pydantic model."""

    def test_construction_with_required_fields(self):
        """EscalationConfig should construct with only max_retries_before_escalate."""
        from engine.interfaces.escalation import EscalationConfig

        config = EscalationConfig(max_retries_before_escalate=3)

        assert config.max_retries_before_escalate == 3
        assert config.escalation_reason is None
        assert config.escalation_metadata == {}

    def test_construction_with_all_fields(self):
        """EscalationConfig should support all optional fields."""
        from engine.interfaces.escalation import EscalationConfig

        config = EscalationConfig(
            max_retries_before_escalate=5,
            escalation_reason="Critical failure threshold exceeded",
            escalation_metadata={"team": "infra", "priority": "high"},
        )

        assert config.max_retries_before_escalate == 5
        assert config.escalation_reason == "Critical failure threshold exceeded"
        assert config.escalation_metadata["team"] == "infra"
        assert config.escalation_metadata["priority"] == "high"

    def test_defaults(self):
        """EscalationConfig should have sensible defaults."""
        from engine.interfaces.escalation import EscalationConfig

        config = EscalationConfig(max_retries_before_escalate=2)

        assert config.escalation_reason is None
        assert config.escalation_metadata == {}

    def test_validation_error_on_missing_required_field(self):
        """EscalationConfig should raise ValidationError if max_retries_before_escalate is missing."""
        from engine.interfaces.escalation import EscalationConfig

        with pytest.raises(ValidationError):
            EscalationConfig()  # type: ignore


# === EscalationRecord Tests ===


class TestEscalationRecord:
    """Test EscalationRecord Pydantic model."""

    def test_construction_with_required_fields(self):
        """EscalationRecord should construct with all required fields."""
        from engine.interfaces.escalation import EscalationRecord

        failure = FailureContext(
            task_id="task-123",
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        record = EscalationRecord(
            task_id="task-123",
            capability="echo",
            total_attempts=4,
            failure_history=[failure],
            escalated_at=datetime.now(),
        )

        assert record.task_id == "task-123"
        assert record.capability == "echo"
        assert record.total_attempts == 4
        assert len(record.failure_history) == 1
        assert record.failure_history[0].attempt == 1
        assert record.reason is None

    def test_construction_with_optional_fields(self):
        """EscalationRecord should support optional reason field."""
        from engine.interfaces.escalation import EscalationRecord

        now = datetime.now()
        record = EscalationRecord(
            task_id="task-456",
            capability="http",
            total_attempts=5,
            failure_history=[],
            escalated_at=now,
            reason="Too many network timeouts",
        )

        assert record.reason == "Too many network timeouts"
        assert record.escalated_at == now

    def test_round_trip_serialization(self):
        """EscalationRecord should be JSON-serializable and reconstructable."""
        from engine.interfaces.escalation import EscalationRecord

        failure1 = FailureContext(
            task_id="task-789",
            capability="filesystem",
            attempt=1,
            max_retries=2,
            error_type="IOError",
            error_message="disk full",
        )
        failure2 = FailureContext(
            task_id="task-789",
            capability="filesystem",
            attempt=2,
            max_retries=2,
            error_type="IOError",
            error_message="disk full",
        )

        original = EscalationRecord(
            task_id="task-789",
            capability="filesystem",
            total_attempts=3,
            failure_history=[failure1, failure2],
            escalated_at=datetime.now(),
            reason="Persistent storage failure",
        )

        # Serialize to dict
        data = original.model_dump()
        assert isinstance(data, dict)
        assert data["task_id"] == "task-789"
        assert data["total_attempts"] == 3
        assert len(data["failure_history"]) == 2

        # Reconstruct from dict
        reconstructed = EscalationRecord(**data)
        assert reconstructed.task_id == original.task_id
        assert reconstructed.capability == original.capability
        assert reconstructed.total_attempts == original.total_attempts
        assert len(reconstructed.failure_history) == len(original.failure_history)
        assert reconstructed.reason == original.reason


# === ThresholdEscalationPolicy Tests ===


class TestThresholdEscalationPolicy:
    """Test ThresholdEscalationPolicy implementation."""

    def test_should_escalate_below_threshold(self):
        """Should not escalate when failure count is below threshold."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(max_retries_before_escalate=3)
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=2,
            max_retries=5,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=1,
                max_retries=5,
                error_type="ValueError",
                error_message="error 1",
            ),
        ]

        should_escalate = policy.should_escalate(task, history)
        assert should_escalate is False

    def test_should_escalate_at_threshold(self):
        """Should escalate when failure count reaches threshold."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(max_retries_before_escalate=3)
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=3,
            max_retries=5,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=i,
                max_retries=5,
                error_type="ValueError",
                error_message=f"error {i}",
            )
            for i in range(1, 4)
        ]

        should_escalate = policy.should_escalate(task, history)
        assert should_escalate is True

    def test_should_escalate_above_threshold(self):
        """Should escalate when failure count exceeds threshold."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(max_retries_before_escalate=2)
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=5,
            max_retries=10,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=i,
                max_retries=10,
                error_type="ValueError",
                error_message=f"error {i}",
            )
            for i in range(1, 6)
        ]

        should_escalate = policy.should_escalate(task, history)
        assert should_escalate is True

    def test_build_record_populates_full_history(self):
        """build_record should include all failure history."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(max_retries_before_escalate=2)
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=3,
            max_retries=5,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=i,
                max_retries=5,
                error_type="ValueError",
                error_message=f"error {i}",
            )
            for i in range(1, 4)
        ]

        record = policy.build_record(task, history)

        assert record.task_id == task.task_id
        assert record.capability == "echo"
        assert record.total_attempts == 3
        assert len(record.failure_history) == 3
        assert record.failure_history[0].attempt == 1
        assert record.failure_history[1].attempt == 2
        assert record.failure_history[2].attempt == 3

    def test_build_record_sets_timestamp(self):
        """build_record should set escalated_at timestamp."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(max_retries_before_escalate=1)
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=2,
            max_retries=3,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=1,
                max_retries=3,
                error_type="ValueError",
                error_message="error",
            ),
        ]

        before = datetime.now()
        record = policy.build_record(task, history)
        after = datetime.now()

        assert before <= record.escalated_at <= after

    def test_build_record_uses_config_reason(self):
        """build_record should use reason from config if provided."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(
            max_retries_before_escalate=2,
            escalation_reason="Custom escalation policy triggered",
        )
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=2,
            max_retries=3,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=1,
                max_retries=3,
                error_type="ValueError",
                error_message="error",
            ),
        ]

        record = policy.build_record(task, history)

        assert record.reason == "Custom escalation policy triggered"

    def test_build_record_default_reason_when_none(self):
        """build_record should provide default reason when config.reason is None."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        config = EscalationConfig(max_retries_before_escalate=1)
        policy = ThresholdEscalationPolicy(config)

        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=3,
        )

        history = [
            FailureContext(
                task_id=task.task_id,
                capability="echo",
                attempt=1,
                max_retries=3,
                error_type="ValueError",
                error_message="error",
            ),
        ]

        record = policy.build_record(task, history)

        # Should have some default reason (spec doesn't mandate exact text)
        assert record.reason is not None
        assert len(record.reason) > 0


# === Supervisor Integration Tests ===


class TestSupervisorEscalation:
    """Test supervisor integration with escalation policy."""

    def test_task_escalates_when_policy_triggers(self, tmp_path: Path):
        """Task should transition to ESCALATED when policy returns should_escalate=True."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        class FailingCapability(Capability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(
                    name="failing",
                    description="Always fails.",
                    risk_level=RiskLevel.LOW,
                )

            def execute(self, payload: dict, context) -> CapabilityResult:
                raise ValueError("Intentional failure")

        registry = CapabilityRegistry()
        registry.register(FailingCapability())

        config = EscalationConfig(max_retries_before_escalate=2)
        policy = ThresholdEscalationPolicy(config)

        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            escalation_policy=policy,
        )

        task = supervisor.run_submission(
            TaskSubmission(
                name="Will escalate",
                capability="failing",
                max_retries=3,
            )
        )

        assert task.status == TaskStatus.ESCALATED

    def test_escalation_record_stored_as_result(self, tmp_path: Path):
        """EscalationRecord should be stored in task result when escalated."""
        from engine.interfaces.escalation import EscalationConfig, EscalationRecord
        from engine.runtime.escalation import ThresholdEscalationPolicy

        class FailingCapability(Capability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(
                    name="failing",
                    description="Always fails.",
                    risk_level=RiskLevel.LOW,
                )

            def execute(self, payload: dict, context) -> CapabilityResult:
                raise ValueError("Intentional failure")

        registry = CapabilityRegistry()
        registry.register(FailingCapability())

        config = EscalationConfig(
            max_retries_before_escalate=1,
            escalation_reason="Test escalation",
        )
        policy = ThresholdEscalationPolicy(config)

        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            escalation_policy=policy,
        )

        task = supervisor.run_submission(
            TaskSubmission(
                name="Will escalate",
                capability="failing",
                max_retries=2,
            )
        )

        assert task.status == TaskStatus.ESCALATED
        assert task.result is not None
        assert task.result.success is False

        # Result metadata should contain escalation record
        assert "escalation_record" in task.result.metadata
        record_data = task.result.metadata["escalation_record"]

        # Reconstruct to validate structure
        record = EscalationRecord(**record_data)
        assert record.task_id == task.task_id
        assert record.capability == "failing"
        assert record.total_attempts >= 2
        assert len(record.failure_history) >= 1
        assert record.reason == "Test escalation"

    def test_task_fails_without_escalation_policy(self, tmp_path: Path):
        """Task should transition to FAILED (not ESCALATED) when no policy is set."""

        class FailingCapability(Capability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(
                    name="failing",
                    description="Always fails.",
                    risk_level=RiskLevel.LOW,
                )

            def execute(self, payload: dict, context) -> CapabilityResult:
                raise ValueError("Intentional failure")

        registry = CapabilityRegistry()
        registry.register(FailingCapability())

        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            # No escalation_policy set
        )

        task = supervisor.run_submission(
            TaskSubmission(
                name="Will fail",
                capability="failing",
                max_retries=2,
            )
        )

        assert task.status == TaskStatus.FAILED
        assert task.status != TaskStatus.ESCALATED

    def test_task_retries_below_escalation_threshold(self, tmp_path: Path):
        """Task should retry normally when below escalation threshold."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        class FailingTwiceCapability(Capability):
            def __init__(self):
                super().__init__()
                self.call_count = 0

            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(
                    name="failing_twice",
                    description="Fails twice, succeeds third time.",
                    risk_level=RiskLevel.LOW,
                )

            def execute(self, payload: dict, context) -> CapabilityResult:
                self.call_count += 1
                if self.call_count < 3:
                    raise ValueError(f"Failure {self.call_count}")
                return CapabilityResult(output={"success": True})

        capability = FailingTwiceCapability()
        registry = CapabilityRegistry()
        registry.register(capability)

        config = EscalationConfig(max_retries_before_escalate=5)
        policy = ThresholdEscalationPolicy(config)

        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            escalation_policy=policy,
        )

        task = supervisor.run_submission(
            TaskSubmission(
                name="Will succeed on retry",
                capability="failing_twice",
                max_retries=3,
            )
        )

        assert task.status == TaskStatus.COMPLETED
        assert capability.call_count == 3
        assert task.attempt == 3

    def test_audit_trail_contains_escalation_entry(self, tmp_path: Path):
        """Audit trail should contain escalated action when task escalates."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        class FailingCapability(Capability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(
                    name="failing",
                    description="Always fails.",
                    risk_level=RiskLevel.LOW,
                )

            def execute(self, payload: dict, context) -> CapabilityResult:
                raise ValueError("Intentional failure")

        registry = CapabilityRegistry()
        registry.register(FailingCapability())

        config = EscalationConfig(max_retries_before_escalate=1)
        policy = ThresholdEscalationPolicy(config)

        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            escalation_policy=policy,
        )

        task = supervisor.run_submission(
            TaskSubmission(
                name="Will escalate",
                capability="failing",
                max_retries=2,
            )
        )

        assert task.status == TaskStatus.ESCALATED

        escalation_entries = [e for e in task.audit_trail if e.action == "escalated"]
        assert len(escalation_entries) == 1
        assert escalation_entries[0].to_status == TaskStatus.ESCALATED

    def test_task_escalated_event_emitted(self, tmp_path: Path):
        """TASK_ESCALATED event should be emitted exactly once when task escalates."""
        from engine.interfaces.escalation import EscalationConfig
        from engine.runtime.escalation import ThresholdEscalationPolicy

        class FailingCapability(Capability):
            @property
            def descriptor(self) -> CapabilityDescriptor:
                return CapabilityDescriptor(
                    name="failing",
                    description="Always fails.",
                    risk_level=RiskLevel.LOW,
                )

            def execute(self, payload: dict, context) -> CapabilityResult:
                raise ValueError("Intentional failure")

        class CapturingEventBus:
            def __init__(self):
                self.events: list[TaskEvent] = []

            def emit(self, event: TaskEvent) -> None:
                self.events.append(event)

        registry = CapabilityRegistry()
        registry.register(FailingCapability())

        config = EscalationConfig(max_retries_before_escalate=1)
        policy = ThresholdEscalationPolicy(config)

        event_bus = CapturingEventBus()

        supervisor = TaskSupervisor(
            registry=registry,
            store=MemoryTaskStore(),
            workdir=tmp_path,
            event_bus=event_bus,
            escalation_policy=policy,
        )

        task = supervisor.run_submission(
            TaskSubmission(
                name="Will escalate",
                capability="failing",
                max_retries=2,
            )
        )

        assert task.status == TaskStatus.ESCALATED

        escalated_events = [e for e in event_bus.events if e.event_type == EventType.TASK_ESCALATED]
        assert len(escalated_events) == 1
        assert escalated_events[0].task_id == task.task_id
        assert escalated_events[0].status == TaskStatus.ESCALATED
