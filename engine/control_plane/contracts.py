"""Versioned control-plane contracts for external operator surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from engine.interfaces.capability import CapabilityDescriptor, CapabilityExecutionControls
from engine.interfaces.event import TaskEvent
from engine.interfaces.task import AuditEntry, TaskRecord, TaskResult, TaskStatus
from engine.interfaces.workflow import WorkflowStatus
from engine.registry.capabilities import CapabilityRegistry


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _status_value(value: TaskStatus | WorkflowStatus | None) -> str | None:
    if value is None:
        return None
    return value.value


def _workflow_status(records: list[TaskRecord]) -> WorkflowStatus:
    if not records:
        return WorkflowStatus.PENDING

    statuses = {record.status for record in records}
    if statuses == {TaskStatus.PENDING}:
        return WorkflowStatus.PENDING
    if statuses == {TaskStatus.COMPLETED}:
        return WorkflowStatus.COMPLETED

    active_statuses = {
        TaskStatus.PENDING,
        TaskStatus.RUNNING,
        TaskStatus.APPROVED,
        TaskStatus.AWAITING_APPROVAL,
    }
    if statuses & active_statuses:
        return WorkflowStatus.RUNNING

    failed_statuses = {
        TaskStatus.FAILED,
        TaskStatus.POLICY_DENIED,
        TaskStatus.CANCELLED,
        TaskStatus.ESCALATED,
    }
    if statuses <= failed_statuses:
        return WorkflowStatus.FAILED
    if statuses & failed_statuses:
        return WorkflowStatus.PARTIAL
    return WorkflowStatus.PARTIAL


def _component_issues(component: object) -> list[str]:
    checker = getattr(component, "health_check", None)
    if checker is None:
        return []
    return list(checker())


class ControlPlaneAuditEntryV1(BaseModel):
    timestamp: datetime
    actor: str
    action: str
    from_status: str | None = None
    to_status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_audit_entry(cls, entry: AuditEntry) -> ControlPlaneAuditEntryV1:
        return cls(
            timestamp=entry.timestamp,
            actor=entry.actor,
            action=entry.action,
            from_status=_status_value(entry.from_status),
            to_status=_status_value(entry.to_status),
            metadata=dict(entry.metadata),
        )


class ControlPlaneTaskResultV1(BaseModel):
    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_result(cls, result: TaskResult) -> ControlPlaneTaskResultV1:
        return cls(
            success=result.success,
            output=result.output,
            error=result.error,
            metadata=dict(result.metadata),
            started_at=result.started_at,
            completed_at=result.completed_at,
        )


class ControlPlaneTaskV1(BaseModel):
    task_id: str
    name: str
    capability: str
    status: str
    attempt: int
    max_retries: int
    workflow_id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    result: ControlPlaneTaskResultV1 | None = None
    audit_trail: list[ControlPlaneAuditEntryV1] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    @classmethod
    def from_task(cls, task: TaskRecord) -> ControlPlaneTaskV1:
        return cls(
            task_id=task.task_id,
            name=task.name,
            capability=task.capability,
            status=task.status.value,
            attempt=task.attempt,
            max_retries=task.max_retries,
            workflow_id=task.workflow_id,
            input=dict(task.input),
            metadata=dict(task.metadata),
            result=(
                ControlPlaneTaskResultV1.from_result(task.result)
                if task.result is not None
                else None
            ),
            audit_trail=[
                ControlPlaneAuditEntryV1.from_audit_entry(entry)
                for entry in task.audit_trail
            ],
            created_at=task.created_at,
            updated_at=task.updated_at,
            archived_at=task.archived_at,
        )


class ControlPlaneApprovalV1(BaseModel):
    task_id: str
    task_name: str
    capability: str
    workflow_id: str | None = None
    requested_at: datetime
    audit_entries: list[ControlPlaneAuditEntryV1] = Field(default_factory=list)

    @classmethod
    def from_task(cls, task: TaskRecord) -> ControlPlaneApprovalV1:
        return cls(
            task_id=task.task_id,
            task_name=task.name,
            capability=task.capability,
            workflow_id=task.workflow_id,
            requested_at=task.updated_at,
            audit_entries=[
                ControlPlaneAuditEntryV1.from_audit_entry(entry)
                for entry in task.audit_trail
            ],
        )


class ControlPlaneWorkflowStepV1(BaseModel):
    task_id: str
    name: str
    capability: str
    status: str
    attempt: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_task(cls, task: TaskRecord) -> ControlPlaneWorkflowStepV1:
        return cls(
            task_id=task.task_id,
            name=task.name,
            capability=task.capability,
            status=task.status.value,
            attempt=task.attempt,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class ControlPlaneWorkflowTraceV1(BaseModel):
    workflow_id: str
    status: str
    task_count: int
    tasks: list[ControlPlaneWorkflowStepV1] = Field(default_factory=list)

    @classmethod
    def from_records(
        cls,
        workflow_id: str,
        records: list[TaskRecord],
    ) -> ControlPlaneWorkflowTraceV1:
        ordered_records = sorted(records, key=lambda record: (record.created_at, record.task_id))
        return cls(
            workflow_id=workflow_id,
            status=_workflow_status(ordered_records).value,
            task_count=len(ordered_records),
            tasks=[ControlPlaneWorkflowStepV1.from_task(task) for task in ordered_records],
        )


class ControlPlaneCapabilityExecutionControlsV1(BaseModel):
    timeout_seconds: float | None = None
    min_interval_seconds: float | None = None

    @classmethod
    def from_controls(
        cls,
        controls: CapabilityExecutionControls,
    ) -> ControlPlaneCapabilityExecutionControlsV1:
        return cls(
            timeout_seconds=controls.timeout_seconds,
            min_interval_seconds=controls.min_interval_seconds,
        )


class ControlPlaneCapabilityV1(BaseModel):
    name: str
    description: str
    risk_level: str
    tags: list[str] = Field(default_factory=list)
    execution_controls: ControlPlaneCapabilityExecutionControlsV1

    @classmethod
    def from_descriptor(
        cls,
        descriptor: CapabilityDescriptor,
        controls: CapabilityExecutionControls,
    ) -> ControlPlaneCapabilityV1:
        return cls(
            name=descriptor.name,
            description=descriptor.description,
            risk_level=descriptor.risk_level.value,
            tags=list(descriptor.tags),
            execution_controls=ControlPlaneCapabilityExecutionControlsV1.from_controls(controls),
        )


class ControlPlaneHealthComponentV1(BaseModel):
    name: str
    healthy: bool
    detail: str
    issues: list[str] = Field(default_factory=list)


class ControlPlaneSnapshotV1(BaseModel):
    schema_version: str = "v1"
    generated_at: datetime = Field(default_factory=_now)
    tasks: list[ControlPlaneTaskV1] = Field(default_factory=list)
    approvals: list[ControlPlaneApprovalV1] = Field(default_factory=list)
    workflows: list[ControlPlaneWorkflowTraceV1] = Field(default_factory=list)
    capabilities: list[ControlPlaneCapabilityV1] = Field(default_factory=list)
    health: list[ControlPlaneHealthComponentV1] = Field(default_factory=list)


class ControlPlaneEventV1(BaseModel):
    schema_version: str = "v1"
    timestamp: datetime
    event_type: str
    task_id: str
    task_name: str
    capability: str
    status: str
    attempt: int
    workflow_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_task_event(cls, event: TaskEvent) -> ControlPlaneEventV1:
        return cls(
            timestamp=event.timestamp,
            event_type=event.event_type.value,
            task_id=event.task_id,
            task_name=event.task_name,
            capability=event.capability,
            status=event.status.value,
            attempt=event.attempt,
            workflow_id=event.workflow_id,
            error=event.error,
            metadata=dict(event.metadata),
        )


def build_health_components(
    *components: tuple[str, object, str],
) -> list[ControlPlaneHealthComponentV1]:
    return [
        ControlPlaneHealthComponentV1(
            name=name,
            healthy=not issues,
            detail=detail,
            issues=issues,
        )
        for name, component, detail in components
        for issues in [_component_issues(component)]
    ]


def build_control_plane_snapshot(
    *,
    tasks: list[TaskRecord],
    registry: CapabilityRegistry,
    health_components: list[ControlPlaneHealthComponentV1],
) -> ControlPlaneSnapshotV1:
    ordered_tasks = sorted(tasks, key=lambda task: (task.created_at, task.task_id))

    workflows_by_id: dict[str, list[TaskRecord]] = {}
    for task in ordered_tasks:
        if task.workflow_id is None:
            continue
        workflows_by_id.setdefault(task.workflow_id, []).append(task)

    return ControlPlaneSnapshotV1(
        tasks=[ControlPlaneTaskV1.from_task(task) for task in ordered_tasks],
        approvals=[
            ControlPlaneApprovalV1.from_task(task)
            for task in ordered_tasks
            if task.status == TaskStatus.AWAITING_APPROVAL
        ],
        workflows=[
            ControlPlaneWorkflowTraceV1.from_records(workflow_id, records)
            for workflow_id, records in sorted(workflows_by_id.items())
        ],
        capabilities=[
            ControlPlaneCapabilityV1.from_descriptor(
                descriptor,
                registry.execution_controls(descriptor.name),
            )
            for descriptor in registry.list()
        ],
        health=health_components,
    )
