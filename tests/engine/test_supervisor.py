"""Tests for the minimal Conductor Engine runtime."""

from __future__ import annotations

from pathlib import Path
import time

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
    assert [entry.action for entry in task.audit_trail] == ["submitted", "started", "completed"]
    assert task.audit_trail[1].from_status == TaskStatus.PENDING
    assert task.audit_trail[1].to_status == TaskStatus.RUNNING
    assert task.audit_trail[2].from_status == TaskStatus.RUNNING
    assert task.audit_trail[2].to_status == TaskStatus.COMPLETED


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

        def execute(self, payload: SlowInput, context) -> CapabilityResult:
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

        def execute(self, payload: dict, context) -> CapabilityResult:
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
