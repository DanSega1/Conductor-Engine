"""CLI smoke tests for `cond`."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.cond import main
from engine.interfaces.task import AuditEntry, TaskRecord, TaskStatus
from engine.runtime.store import LocalTaskStore


def _save_task(store_file: Path, task: TaskRecord) -> None:
    LocalTaskStore(store_file).save(task)


def test_capability_list_outputs_builtin_capabilities(capsys) -> None:
    exit_code = main(["capability", "list"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "echo" in captured.out
    assert "filesystem" in captured.out
    assert "http" in captured.out


def test_run_executes_task_and_persists_it(tmp_path: Path, capsys) -> None:
    task_file = tmp_path / "task.yaml"
    store_file = tmp_path / "tasks.json"
    task_file.write_text(
        "\n".join(
            [
                "name: Echo from CLI",
                "capability: echo",
                "input:",
                "  message: hello from cond",
            ]
        )
    )

    exit_code = main(["--store", str(store_file), "run", str(task_file)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "completed" in captured.out
    assert "hello from cond" in captured.out
    assert store_file.exists()


def test_health_reports_cli_components(tmp_path: Path, capsys) -> None:
    store_file = tmp_path / "tasks.json"

    exit_code = main(["--store", str(store_file), "health"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "cond health" in captured.out
    assert "registry" in captured.out
    assert "task_store" in captured.out
    assert "supervisor" in captured.out
    assert "healthy" in captured.out


def test_task_list_supports_status_offset_and_limit(tmp_path: Path, capsys) -> None:
    store_file = tmp_path / "tasks.json"
    _save_task(
        store_file,
        TaskRecord(
            task_id="00000000-0000-0000-0000-000000000001",
            name="completed-a",
            capability="echo",
            status=TaskStatus.COMPLETED,
        ),
    )
    _save_task(
        store_file,
        TaskRecord(
            task_id="00000000-0000-0000-0000-000000000002",
            name="completed-b",
            capability="echo",
            status=TaskStatus.COMPLETED,
        ),
    )
    _save_task(
        store_file,
        TaskRecord(
            task_id="00000000-0000-0000-0000-000000000003",
            name="failed-c",
            capability="echo",
            status=TaskStatus.FAILED,
        ),
    )

    exit_code = main(
        [
            "--store",
            str(store_file),
            "task",
            "list",
            "--status",
            "completed",
            "--offset",
            "1",
            "--limit",
            "1",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "completed-b" in captured.out
    assert "completed-a" not in captured.out
    assert "failed-c" not in captured.out


def test_task_list_outputs_persisted_tasks_and_attempts(tmp_path: Path, capsys) -> None:
    store_file = tmp_path / "tasks.json"
    store = LocalTaskStore(store_file)
    store.save(
        TaskRecord(
            name="Retrying task",
            capability="echo",
            status=TaskStatus.FAILED,
            attempt=2,
            max_retries=2,
        )
    )
    store.save(
        TaskRecord(
            name="Happy task",
            capability="echo",
            status=TaskStatus.COMPLETED,
            attempt=1,
        )
    )

    exit_code = main(["--store", str(store_file), "task", "list"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Retrying task" in captured.out
    assert "Happy task" in captured.out
    assert "failed" in captured.out
    assert "completed" in captured.out
    assert "2 / 3" in captured.out


def test_task_show_displays_workflow_and_audit_for_prefix(tmp_path: Path, capsys) -> None:
    store_file = tmp_path / "tasks.json"
    _save_task(
        store_file,
        TaskRecord(
            task_id="11111111-1111-1111-1111-111111111111",
            name="awaiting-approval",
            capability="echo",
            status=TaskStatus.AWAITING_APPROVAL,
            workflow_id="wf-123",
            audit_trail=[
                AuditEntry(
                    actor="policy",
                    action="awaiting_approval",
                    to_status=TaskStatus.AWAITING_APPROVAL,
                )
            ],
        ),
    )

    exit_code = main(["--store", str(store_file), "task", "show", "11111111"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "wf-123" in captured.out
    assert "policy" in captured.out
    assert "audit trail" in captured.out
    assert "awaiting approval" in captured.out


def test_task_approve_runs_task_from_prefix(tmp_path: Path, capsys) -> None:
    store_file = tmp_path / "tasks.json"
    task_id = "22222222-2222-2222-2222-222222222222"
    _save_task(
        store_file,
        TaskRecord(
            task_id=task_id,
            name="approval-echo",
            capability="echo",
            input={"message": "approved hello"},
            status=TaskStatus.AWAITING_APPROVAL,
        ),
    )

    exit_code = main(["--store", str(store_file), "task", "approve", "22222222"])

    captured = capsys.readouterr()
    stored = LocalTaskStore(store_file).get(task_id)

    assert exit_code == 0
    assert "completed" in captured.out
    assert "approved hello" in captured.out
    assert stored is not None
    assert stored.status == TaskStatus.COMPLETED
    assert any(entry.action == "approved" for entry in stored.audit_trail)


def test_task_cancel_marks_task_cancelled(tmp_path: Path, capsys) -> None:
    store_file = tmp_path / "tasks.json"
    task_id = "33333333-3333-3333-3333-333333333333"
    _save_task(
        store_file,
        TaskRecord(
            task_id=task_id,
            name="cancel-me",
            capability="echo",
            status=TaskStatus.AWAITING_APPROVAL,
        ),
    )

    exit_code = main(
        [
            "--store",
            str(store_file),
            "task",
            "cancel",
            "33333333",
            "--reason",
            "not now",
        ]
    )

    captured = capsys.readouterr()
    stored = LocalTaskStore(store_file).get(task_id)

    assert exit_code == 0
    assert "cancelled" in captured.out
    assert "not now" in captured.out
    assert stored is not None
    assert stored.status == TaskStatus.CANCELLED


def test_help_without_topic_lists_commands_and_capabilities(capsys) -> None:
    exit_code = main(["help"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "cond help" in captured.out
    assert "workflow" in captured.out
    assert "health" in captured.out
    assert "echo" in captured.out
    assert "man cond" in captured.out


def test_help_echo_shows_capability_schema(capsys) -> None:
    exit_code = main(["help", "echo"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Return the provided message unchanged." in captured.out
    assert "message" in captured.out
    assert "Example task" in captured.out
    assert "man cond" in captured.out


def test_help_task_shows_new_task_commands(capsys) -> None:
    exit_code = main(["help", "task"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "cond task show <task-id-or-prefix>" in captured.out
    assert "cond task approve <task-id-or-prefix>" in captured.out
    assert "cond task cancel <task-id-or-prefix>" in captured.out
    assert "man cond" in captured.out


def test_help_workflow_shows_command_manual(capsys) -> None:
    exit_code = main(["help", "workflow"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "cond workflow run <workflow-file>" in captured.out
    assert "goal: Echo two messages in sequence" in captured.out
    assert "man cond" in captured.out


def test_help_unknown_topic_returns_error(capsys) -> None:
    exit_code = main(["help", "not-a-topic"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Unknown help topic: not-a-topic" in captured.err


# NOTE: requires McManus slice 2 implementation
# ESCALATED must be added to STATUS_STYLES and STATUS_LABELS in cli/cond.py before
# these tests can pass — otherwise _status_text raises KeyError for TaskStatus.ESCALATED.
@pytest.mark.xfail(reason="requires McManus slice 2: ESCALATED in CLI STATUS_STYLES/LABELS", strict=False)
def test_task_list_shows_escalated_tasks_not_silently_hidden(tmp_path: Path, capsys) -> None:
    """ESCALATED tasks must appear in `cond task list` output with a distinct marker."""
    store_file = tmp_path / "tasks.json"
    _save_task(
        store_file,
        TaskRecord(
            task_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            name="escalated-task",
            capability="echo",
            status=TaskStatus.ESCALATED,
        ),
    )
    _save_task(
        store_file,
        TaskRecord(
            task_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            name="completed-task",
            capability="echo",
            status=TaskStatus.COMPLETED,
        ),
    )

    exit_code = main(["--store", str(store_file), "task", "list"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "escalated-task" in captured.out
    assert "escalated" in captured.out


# NOTE: requires McManus slice 2 implementation
# Displaying ESCALATED tasks requires STATUS_STYLES/STATUS_LABELS entries.
@pytest.mark.xfail(reason="requires McManus slice 2: ESCALATED in CLI STATUS_STYLES/LABELS", strict=False)
def test_task_list_status_filter_escalated_returns_only_escalated(
    tmp_path: Path, capsys
) -> None:
    """--status escalated must return only ESCALATED tasks and exclude all others."""
    store_file = tmp_path / "tasks.json"
    _save_task(
        store_file,
        TaskRecord(
            task_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            name="escalated-only",
            capability="echo",
            status=TaskStatus.ESCALATED,
        ),
    )
    _save_task(
        store_file,
        TaskRecord(
            task_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
            name="should-not-appear",
            capability="echo",
            status=TaskStatus.FAILED,
        ),
    )

    exit_code = main(["--store", str(store_file), "task", "list", "--status", "escalated"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "escalated-only" in captured.out
    assert "should-not-appear" not in captured.out
