"""Tests for the minimal Conductor Engine runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.capabilities.echo import EchoCapability
from engine.capabilities.filesystem import FilesystemCapability
from engine.interfaces.task import TaskStatus, TaskSubmission
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
