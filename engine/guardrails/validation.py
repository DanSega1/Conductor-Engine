"""Validation helpers used by the minimal runtime."""

from __future__ import annotations

from pathlib import Path

from engine.interfaces.capability import Capability
from engine.interfaces.task import TaskSubmission
from engine.registry.capabilities import CapabilityRegistry


def validate_task_submission(
    submission: TaskSubmission,
    registry: CapabilityRegistry,
) -> Capability:
    """Validate a task request and resolve its target capability."""
    if not submission.name.strip():
        raise ValueError("Task name must not be empty")
    if not submission.capability.strip():
        raise ValueError("Task capability must not be empty")

    try:
        capability = registry.get(submission.capability)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc

    capability.validate_input(submission.input)
    return capability


def ensure_local_path(path: str, base_path: Path) -> Path:
    """Resolve a path and reject traversal outside the configured root."""
    candidate = Path(path)
    resolved = candidate if candidate.is_absolute() else (base_path / candidate)
    resolved = resolved.resolve()
    root = base_path.resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path '{path}' escapes the configured filesystem root") from exc

    return resolved
