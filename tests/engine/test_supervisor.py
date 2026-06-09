"""Tests for the minimal Conductor Engine runtime."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from pydantic import BaseModel
import pytest

from engine.capabilities.echo import EchoCapability
from engine.capabilities.filesystem import FilesystemCapability
from engine.interfaces.capability import (
    Capability,
    CapabilityDescriptor,
    CapabilityExecutionControls,
    CapabilityResult,
)
from engine.interfaces.event import EventType, TaskEvent
from engine.interfaces.policy import PolicyDecision, PolicyDecisionType
from engine.interfaces.task import RiskLevel, TaskRecord, TaskStatus, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor


def test_supervisor_runs_echo_task_successfully(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    task = supervisor.run_submission(
        TaskSubmission(name="Echo hello", capability="echo", input={"message": "hello"})
    )

    assert task.status == TaskStatus.COMPLETED
    assert task.result is not None
    assert task.result.output == {"message": "hello"}


def test_supervisor_marks_failed_task_when_capability_raises(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(FilesystemCapability(base_path=tmp_path))
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    task = supervisor.run_submission(
        TaskSubmission(
            name="Read missing file",
            capability="filesystem",
            input={"action": "read_text", "path": "missing.txt"},
        )
    )

    assert task.status == TaskStatus.FAILED
    assert task.result is not None
    assert "No such file" in (task.result.error or "")


def test_filesystem_capability_blocks_path_escape(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(FilesystemCapability(base_path=tmp_path))
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    with pytest.raises(ValueError, match="escapes the configured filesystem root"):
        supervisor.submit(
            TaskSubmission(
                name="Escape",
                capability="filesystem",
                input={"action": "read_text", "path": "../secret.txt"},
            )
        )


def test_supervisor_preserves_existing_workflow_id_during_execution(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    store = MemoryTaskStore()
    supervisor = TaskSupervisor(registry=registry, store=store, workdir=tmp_path)

    task = TaskRecord(
        name="Workflow echo",
        capability="echo",
        input={"message": "hello"},
        workflow_id="wf-123",
    )
    store.save(task)
    supervisor.queue.enqueue(task.task_id)

    result = supervisor.run_next()

    assert result.status == TaskStatus.COMPLETED
    assert result.workflow_id == "wf-123"
    stored = store.get(task.task_id)
    assert stored is not None
    assert stored.workflow_id == "wf-123"


def test_supervisor_writes_audit_trail_and_workflow_id(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    task = supervisor.run_submission(
        TaskSubmission(
            name="Echo hello",
            capability="echo",
            input={"message": "hello"},
            workflow_id="wf-123",
        )
    )

    assert task.workflow_id == "wf-123"
    assert [entry.action for entry in task.audit_trail] == [
        "submitted",
        "allowed",
        "started",
        "completed",
    ]
    assert task.audit_trail[1].from_status == TaskStatus.PENDING
    assert task.audit_trail[1].to_status == TaskStatus.PENDING
    assert task.audit_trail[2].from_status == TaskStatus.PENDING
    assert task.audit_trail[2].to_status == TaskStatus.RUNNING
    assert task.audit_trail[3].from_status == TaskStatus.RUNNING
    assert task.audit_trail[3].to_status == TaskStatus.COMPLETED


def test_supervisor_records_policy_allow_in_audit_trail(tmp_path: Path) -> None:
    class AllowPolicy:
        def evaluate(self, task, context) -> PolicyDecision:
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                reason="approved by policy",
                metadata={"policy": "allow-all"},
            )

    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        policy_engine=AllowPolicy(),
    )

    task = supervisor.run_submission(
        TaskSubmission(name="Echo hello", capability="echo", input={"message": "hello"})
    )

    allowed_entries = [entry for entry in task.audit_trail if entry.action == "allowed"]
    assert len(allowed_entries) == 1
    assert allowed_entries[0].from_status == TaskStatus.PENDING
    assert allowed_entries[0].to_status == TaskStatus.PENDING
    assert allowed_entries[0].metadata["policy"] == "allow-all"
    assert allowed_entries[0].metadata["reason"] == "approved by policy"


def test_supervisor_persists_policy_denied_tasks_with_audit_and_event(tmp_path: Path) -> None:
    class DenyPolicy:
        def evaluate(self, task, context) -> PolicyDecision:
            return PolicyDecision(
                decision=PolicyDecisionType.DENY,
                reason="echo disabled",
                metadata={"policy": "test"},
            )

    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        event_bus=CapturingBus(),
        policy_engine=DenyPolicy(),
    )

    task = supervisor.run_submission(
        TaskSubmission(name="Echo hello", capability="echo", input={"message": "hello"})
    )

    stored = supervisor.store.get(task.task_id)

    assert stored is not None
    assert task.status == TaskStatus.POLICY_DENIED
    assert task.result is not None
    assert task.result.error == "echo disabled"
    assert task.audit_trail[-1].action == "denied"
    assert task.audit_trail[-1].to_status == TaskStatus.POLICY_DENIED
    assert captured[-1].event_type == EventType.TASK_POLICY_DENIED


def test_supervisor_approval_flow_runs_after_approval(tmp_path: Path) -> None:
    class ApprovalPolicy:
        def evaluate(self, task, context) -> PolicyDecision:
            return PolicyDecision(
                decision=PolicyDecisionType.REQUIRE_APPROVAL,
                reason="needs human review",
                metadata={"gate": "manual"},
            )

    captured: list[TaskEvent] = []

    class CapturingBus:
        def emit(self, event: TaskEvent) -> None:
            captured.append(event)

    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        event_bus=CapturingBus(),
        policy_engine=ApprovalPolicy(),
    )

    awaiting = supervisor.run_submission(
        TaskSubmission(name="Echo hello", capability="echo", input={"message": "hello"})
    )
    approved = supervisor.approve_task(awaiting.task_id, actor="dan")

    assert awaiting.status == TaskStatus.AWAITING_APPROVAL
    assert approved.status == TaskStatus.COMPLETED
    assert [entry.action for entry in approved.audit_trail] == [
        "submitted",
        "awaiting_approval",
        "approved",
        "started",
        "completed",
    ]
    assert [event.event_type for event in captured] == [
        EventType.TASK_AWAITING_APPROVAL,
        EventType.TASK_APPROVED,
        EventType.TASK_STARTED,
        EventType.TASK_COMPLETED,
    ]


def test_supervisor_list_tasks_exposes_pagination_and_status_filter(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    for index in range(3):
        supervisor.run_submission(
            TaskSubmission(
                name=f"Echo {index}",
                capability="echo",
                input={"message": f"hello-{index}"},
            )
        )

    page = supervisor.list_tasks(limit=1, offset=1, status=TaskStatus.COMPLETED)

    assert len(page) == 1
    assert page[0].status == TaskStatus.COMPLETED


def test_supervisor_can_cancel_waiting_approval_task(tmp_path: Path) -> None:
    class ApprovalPolicy:
        def evaluate(self, task, context) -> PolicyDecision:
            return PolicyDecision(decision=PolicyDecisionType.REQUIRE_APPROVAL)

    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        policy_engine=ApprovalPolicy(),
    )

    task = supervisor.run_submission(
        TaskSubmission(name="Echo hello", capability="echo", input={"message": "hello"})
    )
    cancelled = supervisor.cancel_task(task.task_id, actor="dan", reason="not now")

    assert cancelled.status == TaskStatus.CANCELLED
    assert cancelled.result is not None
    assert cancelled.result.error == "not now"
    assert cancelled.audit_trail[-1].action == "cancelled"


def test_supervisor_fails_task_when_capability_soft_timeout_is_exceeded(tmp_path: Path) -> None:
    class SlowInput(BaseModel):
        duration: float

    class SlowCapability(Capability):
        input_model = SlowInput

        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="slow",
                description="Sleep for a controlled duration.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            assert isinstance(payload, SlowInput)
            time.sleep(payload.duration)
            return CapabilityResult(output={"slept": payload.duration})

    registry = CapabilityRegistry()
    registry.register(
        SlowCapability(),
        execution_controls=CapabilityExecutionControls(timeout_seconds=0.01),
    )
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    task = supervisor.run_submission(
        TaskSubmission(name="Too slow", capability="slow", input={"duration": 0.05})
    )

    assert task.status == TaskStatus.FAILED
    assert task.result is not None
    assert "soft timeout" in (task.result.error or "")


def test_supervisor_enforces_per_capability_min_interval(tmp_path: Path) -> None:
    class StampCapability(Capability):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[float] = []

        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="stamp",
                description="Record invocation timestamps.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            self.calls.append(time.monotonic())
            return CapabilityResult(output={"calls": len(self.calls)})

    capability = StampCapability()
    registry = CapabilityRegistry()
    registry.register(
        capability,
        execution_controls=CapabilityExecutionControls(min_interval_seconds=0.05),
    )
    supervisor = TaskSupervisor(registry=registry, store=MemoryTaskStore(), workdir=tmp_path)

    supervisor.run_submission(TaskSubmission(name="first", capability="stamp"))
    supervisor.run_submission(TaskSubmission(name="second", capability="stamp"))

    assert len(capability.calls) == 2
    assert capability.calls[1] - capability.calls[0] >= 0.045


def test_supervisor_records_failure_context_in_audit_trail(tmp_path: Path) -> None:
    """Failure context should be persisted in audit trail before retry decision."""

    class FailingCapability(Capability):
        def __init__(self) -> None:
            super().__init__()
            self.call_count = 0

        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="failing",
                description="Always fails.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            self.call_count += 1
            raise ValueError("Intentional failure")

    registry = CapabilityRegistry()
    registry.register(FailingCapability())
    store = MemoryTaskStore()
    supervisor = TaskSupervisor(registry=registry, store=store, workdir=tmp_path)

    task = supervisor.run_submission(
        TaskSubmission(
            name="Will fail",
            capability="failing",
            input={"test": "data"},
            max_retries=2,
        )
    )

    assert task.status == TaskStatus.FAILED

    # Find failure_recorded audit entries
    failure_entries = [e for e in task.audit_trail if e.action == "failure_recorded"]
    assert len(failure_entries) == 3  # 3 attempts = 3 failures

    # Check first failure context
    first_failure = failure_entries[0].metadata
    assert first_failure["task_id"] == task.task_id
    assert first_failure["capability"] == "failing"
    assert first_failure["attempt"] == 1
    assert first_failure["max_retries"] == 2
    assert first_failure["error_type"] == "ValueError"
    assert first_failure["error_message"] == "Intentional failure"
    assert "input_fingerprint" in first_failure


def test_supervisor_uses_custom_retry_strategy(tmp_path: Path) -> None:
    """Custom retry strategy should be invoked for failure decisions."""
    from engine.interfaces.retry import FailureContext, RetryDecision

    class NoRetryStrategy:
        """Strategy that prevents all retries."""

        def decide(self, task, failure: FailureContext) -> RetryDecision:
            return RetryDecision(
                should_retry=False,
                reason="Custom policy: no retries allowed",
            )

    class FailingCapability(Capability):
        def __init__(self) -> None:
            super().__init__()
            self.call_count = 0

        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="failing",
                description="Always fails.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            self.call_count += 1
            raise ValueError("Intentional failure")

    capability = FailingCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        retry_strategy=NoRetryStrategy(),
    )

    task = supervisor.run_submission(
        TaskSubmission(
            name="Will fail once",
            capability="failing",
            max_retries=5,  # Should be ignored by custom strategy
        )
    )

    assert task.status == TaskStatus.FAILED
    assert capability.call_count == 1  # Only one attempt despite max_retries=5


def test_supervisor_escalates_when_retry_strategy_requests_it(tmp_path: Path) -> None:
    """Task should transition to ESCALATED when retry strategy sets escalate=True."""
    from engine.runtime.retry import DefaultRetryStrategy

    class FailingCapability(Capability):
        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="failing",
                description="Always fails.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            raise ValueError("Intentional failure")

    registry = CapabilityRegistry()
    registry.register(FailingCapability())
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        retry_strategy=DefaultRetryStrategy(enable_escalation=True),
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
    assert "escalation_reason" in task.result.metadata

    # Check escalation event was emitted via audit trail
    escalation_entry = [e for e in task.audit_trail if e.action == "escalated"]
    assert len(escalation_entry) == 1
    assert escalation_entry[0].to_status == TaskStatus.ESCALATED


def test_supervisor_emits_escalated_event(tmp_path: Path) -> None:
    """TASK_ESCALATED event should be emitted on escalation."""
    from engine.runtime.retry import DefaultRetryStrategy

    class FailingCapability(Capability):
        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="failing",
                description="Always fails.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            raise ValueError("Intentional failure")

    class CapturingEventBus:
        def __init__(self) -> None:
            self.events: list[TaskEvent] = []

        def emit(self, event: TaskEvent) -> None:
            self.events.append(event)

    registry = CapabilityRegistry()
    registry.register(FailingCapability())
    event_bus = CapturingEventBus()
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
        event_bus=event_bus,
        retry_strategy=DefaultRetryStrategy(enable_escalation=True),
    )

    task = supervisor.run_submission(
        TaskSubmission(
            name="Will escalate",
            capability="failing",
            max_retries=1,
        )
    )

    assert task.status == TaskStatus.ESCALATED

    escalated_events = [e for e in event_bus.events if e.event_type == EventType.TASK_ESCALATED]
    assert len(escalated_events) == 1
    assert escalated_events[0].task_id == task.task_id
    assert escalated_events[0].status == TaskStatus.ESCALATED


def test_supervisor_default_retry_behavior_unchanged(tmp_path: Path) -> None:
    """Default retry behavior should match pre-Phase-5 supervisor."""
    class FailingTwiceCapability(Capability):
        def __init__(self) -> None:
            super().__init__()
            self.call_count = 0

        @property
        def descriptor(self) -> CapabilityDescriptor:
            return CapabilityDescriptor(
                name="failing_twice",
                description="Fails twice, succeeds third time.",
                risk_level=RiskLevel.LOW,
            )

        def execute(self, payload: BaseModel | dict[str, Any], context) -> CapabilityResult:
            self.call_count += 1
            if self.call_count < 3:
                raise ValueError(f"Failure {self.call_count}")
            return CapabilityResult(output={"success": True})

    capability = FailingTwiceCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    supervisor = TaskSupervisor(
        registry=registry,
        store=MemoryTaskStore(),
        workdir=tmp_path,
    )

    task = supervisor.run_submission(
        TaskSubmission(
            name="Will succeed on retry",
            capability="failing_twice",
            max_retries=2,
        )
    )

    assert task.status == TaskStatus.COMPLETED
    assert capability.call_count == 3
    assert task.attempt == 3
