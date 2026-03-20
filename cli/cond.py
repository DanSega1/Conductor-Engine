"""Minimal CLI for the Conductor Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from engine.interfaces.task import TaskSubmission
from engine.loader import load_capabilities
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import LocalTaskStore
from engine.supervisor.service import TaskSupervisor

DEFAULT_STORE = Path(".conductor/tasks.json")
DEFAULT_CONFIG = Path("config/conductor.capabilities.yaml")


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _load_yaml_or_json(path: str | Path) -> dict[str, Any]:
    task_path = Path(path)
    raw = task_path.read_text()
    if task_path.suffix == ".json":
        return json.loads(raw)
    return yaml.safe_load(raw)


def _resolve_registry(config_path: str | None, workdir: Path) -> CapabilityRegistry:
    if config_path:
        return load_capabilities(config_path, base_path=workdir)
    if DEFAULT_CONFIG.exists():
        return load_capabilities(DEFAULT_CONFIG, base_path=workdir)
    return load_capabilities(base_path=workdir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cond", description="Conductor Engine CLI")
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE),
        help="Path to the local task store JSON file.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the capability config YAML file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute a task file.")
    run_parser.add_argument("task_file", help="Path to a YAML or JSON task file.")

    capability_parser = subparsers.add_parser("capability", help="Inspect capabilities.")
    capability_subparsers = capability_parser.add_subparsers(
        dest="capability_command", required=True
    )
    capability_subparsers.add_parser("list", help="List all available capabilities.")

    task_parser = subparsers.add_parser("task", help="Inspect stored tasks.")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_subparsers.add_parser("list", help="List tasks from the local store.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workdir = Path.cwd()
    registry = _resolve_registry(args.config, workdir)
    store = LocalTaskStore(args.store)
    supervisor = TaskSupervisor(registry=registry, store=store, workdir=workdir)

    if args.command == "run":
        submission = TaskSubmission.model_validate(_load_yaml_or_json(args.task_file))
        task = supervisor.run_submission(submission)
        print(_json_dump(task.model_dump(mode="json")))
        return 0

    if args.command == "capability" and args.capability_command == "list":
        payload = [descriptor.model_dump(mode="json") for descriptor in registry.list()]
        print(_json_dump(payload))
        return 0

    if args.command == "task" and args.task_command == "list":
        payload = [task.model_dump(mode="json") for task in supervisor.list_tasks()]
        print(_json_dump(payload))
        return 0

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
