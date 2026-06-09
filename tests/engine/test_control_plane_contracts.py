"""Tests for versioned control-plane contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from engine.capabilities.echo import EchoCapability
from engine.control_plane import build_control_plane_snapshot, build_health_components
from engine.control_plane.contracts import ControlPlaneEventV1
from engine.interfaces.capability import CapabilityExecutionControls
from engine.interfaces.event import EventType, TaskEvent
from engine.interfaces.task import AuditEntry, TaskRecord, TaskStatus
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.bus import NullEventBus
from engine.runtime.policy import NullPolicyEngine
from engine.runtime.queue import InMemoryTaskQueue
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor


def test_build_control_plane_snapshot_includes_phase4_read_models(tmp_path) -> None:
    registry = CapabilityRegistry()
    registry.register(
        EchoCapability(),
        execution_controls=CapabilityExecutionControls(timeout_seconds=5, min_interval_seconds=1),
    )
    store = MemoryTaskStore()
    queue = InMemoryTaskQueue()
    supervisor = TaskSupervisor(
        registry=registry,
        store=store,
        queue=queue,
        event_bus=NullEventBus(),
        policy_engine=NullPolicyEngine(),
        workdir=tmp_path,
    )

    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    store.save(
        TaskRecord(
            task_id="task-1",
            name="awaiting approval",
            capability="echo",
            status=TaskStatus.AWAITING_APPROVAL,
            workflow_id="wf-1",
            audit_trail=[
                AuditEntry(
                    actor="policy",
                    action="awaiting_approval",
                    to_status=TaskStatus.AWAITING_APPROVAL,
                    timestamp=created_at,
                )
            ],
            created_at=created_at,
            updated_at=created_at,
        )
    )
    store.save(
        TaskRecord(
            task_id="task-2",
            name="done",
            capability="echo",
            status=TaskStatus.COMPLETED,
            workflow_id="wf-1",
            attempt=1,
            created_at=created_at,
            updated_at=created_at,
        )
    )

    snapshot = build_control_plane_snapshot(
        tasks=supervisor.list_tasks(),
        registry=registry,
        health_components=build_health_components(
            ("registry", registry, "1 capabilities loaded"),
            ("task_store", store, "memory"),
            ("queue", queue, "0 queued"),
            ("event_bus", supervisor._bus, "NullEventBus"),
            ("policy", supervisor._policy, "NullPolicyEngine"),
            ("supervisor", supervisor, str(tmp_path)),
        ),
    )

    assert snapshot.schema_version == "v1"
    assert [task.task_id for task in snapshot.tasks] == ["task-1", "task-2"]
    assert [approval.task_id for approval in snapshot.approvals] == ["task-1"]
    assert snapshot.workflows[0].workflow_id == "wf-1"
    assert snapshot.workflows[0].status == "running"
    assert snapshot.capabilities[0].name == "echo"
    assert snapshot.capabilities[0].execution_controls.timeout_seconds == 5
    assert all(component.healthy for component in snapshot.health)


def test_control_plane_event_v1_wraps_task_event() -> None:
    event = TaskEvent(
        event_type=EventType.TASK_FAILED,
        task_id="task-1",
        task_name="broken",
        capability="echo",
        status=TaskStatus.FAILED,
        attempt=2,
        workflow_id="wf-9",
        error="boom",
        metadata={"retryable": False},
    )

    envelope = ControlPlaneEventV1.from_task_event(event)

    assert envelope.schema_version == "v1"
    assert envelope.event_type == "task_failed"
    assert envelope.workflow_id == "wf-9"
    assert envelope.error == "boom"
    assert envelope.metadata == {"retryable": False}
