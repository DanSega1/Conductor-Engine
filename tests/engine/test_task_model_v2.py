"""Tests for TaskRecord extended fields, AuditEntry, TaskStatus additions,
and MemoryTaskStore.list() pagination introduced in the pre-Phase-3 hardening."""

from __future__ import annotations

from datetime import UTC, datetime

from engine.interfaces.task import AuditEntry, TaskRecord, TaskStatus, TaskSubmission
from engine.runtime.store import MemoryTaskStore

# ---------------------------------------------------------------------------
# TaskStatus — new states
# ---------------------------------------------------------------------------


def test_task_status_has_approval_states() -> None:
    assert TaskStatus.AWAITING_APPROVAL == "awaiting_approval"
    assert TaskStatus.APPROVED == "approved"
    assert TaskStatus.POLICY_DENIED == "policy_denied"
    assert TaskStatus.CANCELLED == "cancelled"


def test_task_status_all_eight_values() -> None:
    values = {s.value for s in TaskStatus}
    assert values == {
        "pending",
        "running",
        "completed",
        "failed",
        "awaiting_approval",
        "approved",
        "policy_denied",
        "cancelled",
    }


# ---------------------------------------------------------------------------
# AuditEntry model
# ---------------------------------------------------------------------------


def test_audit_entry_minimal_construction() -> None:
    entry = AuditEntry(actor="supervisor", action="status_change")
    assert entry.actor == "supervisor"
    assert entry.action == "status_change"
    assert entry.from_status is None
    assert entry.to_status is None
    assert entry.metadata == {}
    assert isinstance(entry.timestamp, datetime)


def test_audit_entry_with_status_transition() -> None:
    entry = AuditEntry(
        actor="supervisor",
        action="status_change",
        from_status=TaskStatus.PENDING,
        to_status=TaskStatus.RUNNING,
    )
    assert entry.from_status == TaskStatus.PENDING
    assert entry.to_status == TaskStatus.RUNNING


def test_audit_entry_with_metadata() -> None:
    entry = AuditEntry(
        actor="policy",
        action="denied",
        metadata={"reason": "rate_limit"},
    )
    assert entry.metadata["reason"] == "rate_limit"


def test_audit_entry_approval_transition() -> None:
    entry = AuditEntry(
        actor="user",
        action="approved",
        from_status=TaskStatus.AWAITING_APPROVAL,
        to_status=TaskStatus.APPROVED,
    )
    assert entry.from_status == TaskStatus.AWAITING_APPROVAL
    assert entry.to_status == TaskStatus.APPROVED


# ---------------------------------------------------------------------------
# TaskRecord — new fields: workflow_id, archived_at, audit_trail
# ---------------------------------------------------------------------------


def test_task_record_workflow_id_defaults_none() -> None:
    record = TaskRecord(name="t", capability="echo")
    assert record.workflow_id is None


def test_task_submission_workflow_id_defaults_none() -> None:
    submission = TaskSubmission(name="t", capability="echo")
    assert submission.workflow_id is None


def test_task_submission_workflow_id_can_be_set() -> None:
    submission = TaskSubmission(name="t", capability="echo", workflow_id="wf-123")
    assert submission.workflow_id == "wf-123"


def test_task_record_workflow_id_can_be_set() -> None:
    record = TaskRecord(name="t", capability="echo", workflow_id="wf-001")
    assert record.workflow_id == "wf-001"


def test_task_record_archived_at_defaults_none() -> None:
    record = TaskRecord(name="t", capability="echo")
    assert record.archived_at is None


def test_task_record_archived_at_can_be_set() -> None:
    ts = datetime.now(tz=UTC)
    record = TaskRecord(name="t", capability="echo", archived_at=ts)
    assert record.archived_at == ts


def test_task_record_audit_trail_defaults_empty() -> None:
    record = TaskRecord(name="t", capability="echo")
    assert record.audit_trail == []


def test_task_record_audit_trail_is_independent_between_records() -> None:
    """Each TaskRecord gets its own list — not a shared default."""
    a = TaskRecord(name="a", capability="echo")
    b = TaskRecord(name="b", capability="echo")
    a.audit_trail.append(AuditEntry(actor="supervisor", action="test"))
    assert b.audit_trail == []


def test_task_record_with_full_audit_trail() -> None:
    e1 = AuditEntry(actor="supervisor", action="started", to_status=TaskStatus.RUNNING)
    e2 = AuditEntry(actor="supervisor", action="completed", to_status=TaskStatus.COMPLETED)
    record = TaskRecord(name="t", capability="echo", audit_trail=[e1, e2])
    assert len(record.audit_trail) == 2
    assert record.audit_trail[0].action == "started"
    assert record.audit_trail[1].action == "completed"


def test_task_record_roundtrips_with_new_fields() -> None:
    """Pydantic serialise → deserialise preserves new fields."""
    ts = datetime.now(tz=UTC)
    entry = AuditEntry(actor="supervisor", action="status_change")
    original = TaskRecord(
        name="t",
        capability="echo",
        workflow_id="wf-42",
        archived_at=ts,
        audit_trail=[entry],
    )
    restored = TaskRecord.model_validate(original.model_dump(mode="json"))
    assert restored.workflow_id == "wf-42"
    assert restored.archived_at == ts
    assert len(restored.audit_trail) == 1
    assert restored.audit_trail[0].actor == "supervisor"


# ---------------------------------------------------------------------------
# MemoryTaskStore.list() — pagination and filtering
# ---------------------------------------------------------------------------


def _make_store_with_tasks() -> MemoryTaskStore:
    """Return a store with 5 tasks: 3 completed, 2 failed."""
    store = MemoryTaskStore()
    for i in range(3):
        r = TaskRecord(name=f"task-{i}", capability="echo", status=TaskStatus.COMPLETED)
        store.save(r)
    for i in range(3, 5):
        r = TaskRecord(name=f"task-{i}", capability="echo", status=TaskStatus.FAILED)
        store.save(r)
    return store


def test_list_no_args_returns_all() -> None:
    store = _make_store_with_tasks()
    assert len(store.list()) == 5


def test_list_with_limit() -> None:
    store = _make_store_with_tasks()
    result = store.list(limit=2)
    assert len(result) == 2


def test_list_with_offset() -> None:
    store = _make_store_with_tasks()
    all_tasks = store.list()
    offset_tasks = store.list(offset=2)
    assert len(offset_tasks) == 3
    assert offset_tasks[0].task_id == all_tasks[2].task_id


def test_list_with_status_filter_completed() -> None:
    store = _make_store_with_tasks()
    result = store.list(status="completed")
    assert len(result) == 3
    assert all(r.status == TaskStatus.COMPLETED for r in result)


def test_list_with_status_filter_failed() -> None:
    store = _make_store_with_tasks()
    result = store.list(status="failed")
    assert len(result) == 2
    assert all(r.status == TaskStatus.FAILED for r in result)


def test_list_status_filter_no_match() -> None:
    store = _make_store_with_tasks()
    result = store.list(status="pending")
    assert result == []


def test_list_limit_and_offset_combined() -> None:
    store = _make_store_with_tasks()
    all_tasks = store.list()
    page2 = store.list(limit=2, offset=2)
    assert len(page2) == 2
    assert page2[0].task_id == all_tasks[2].task_id
    assert page2[1].task_id == all_tasks[3].task_id


def test_list_status_filter_with_limit() -> None:
    store = _make_store_with_tasks()
    result = store.list(status="completed", limit=2)
    assert len(result) == 2
    assert all(r.status == TaskStatus.COMPLETED for r in result)


def test_list_status_filter_with_offset() -> None:
    store = _make_store_with_tasks()
    completed = store.list(status="completed")
    offset_completed = store.list(status="completed", offset=1)
    assert len(offset_completed) == 2
    assert offset_completed[0].task_id == completed[1].task_id


def test_list_offset_beyond_length_returns_empty() -> None:
    store = _make_store_with_tasks()
    result = store.list(offset=100)
    assert result == []


def test_list_limit_zero_returns_empty() -> None:
    store = _make_store_with_tasks()
    result = store.list(limit=0)
    assert result == []
