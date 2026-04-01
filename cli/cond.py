"""Minimal CLI for the Conductor Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import yaml

from engine.interfaces.task import TaskSubmission
from engine.interfaces.workflow import PlanStep, WorkflowGoal, WorkflowResult
from engine.loader import load_capabilities
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.store import LocalTaskStore
from engine.supervisor.service import TaskSupervisor
from engine.workflow.agents import LinearPlanner, PassthroughValidator, PassthroughWorker
from engine.workflow.orchestrator import WorkflowOrchestrator

DEFAULT_STORE = Path(".conductor/tasks.json")
DEFAULT_CONFIG = Path("config/conductor.capabilities.yaml")

console = Console()
err_console = Console(stderr=True)


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


def _format_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    compact = json.dumps(value, separators=(",", ":"))
    if len(compact) > 120:
        return compact[:117] + "..."
    return compact


def _attempts_display(attempt: int, max_retries: int) -> str:
    if max_retries > 0:
        return f"{attempt} / {max_retries + 1}"
    return str(attempt)


def _run_panel(task: Any) -> None:
    is_success = task.status == "completed"
    status_text = Text()
    if is_success:
        status_text.append("✓ completed", style="green")
    else:
        status_text.append("✗ failed", style="red")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(min_width=10)
    grid.add_column()

    grid.add_row(Text("status", style="bold"), status_text)
    grid.add_row(Text("capability", style="bold"), task.capability)
    grid.add_row(Text("attempts", style="bold"), _attempts_display(task.attempt, task.max_retries))

    if is_success and task.result and task.result.output is not None:
        grid.add_row(Text("output", style="bold"), _format_output(task.result.output))
    elif not is_success and task.result and task.result.error:
        grid.add_row(Text("error", style="bold"), task.result.error)

    border_style = "green" if is_success else "red"
    console.print(Panel(grid, title=task.name, border_style=border_style))


def _workflow_result_panel(result: WorkflowResult) -> None:
    is_success = result.status == "completed"
    status_text = Text()
    if is_success:
        status_text.append("\u2713 completed", style="green")
    else:
        status_text.append(f"\u2717 {result.status}", style="red")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(min_width=10)
    grid.add_column()

    grid.add_row(Text("goal", style="bold"), result.goal)
    grid.add_row(Text("status", style="bold"), status_text)
    grid.add_row(Text("steps", style="bold"), str(len(result.records)))

    border_style = "green" if is_success else "red"
    console.print(Panel(grid, title="workflow", border_style=border_style))

    for record in result.records:
        _run_panel(record)


def _capability_list_table(registry: CapabilityRegistry) -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
    table.add_column("Name")
    table.add_column("Risk")
    table.add_column("Tags")

    for descriptor in registry.list():
        table.add_row(
            descriptor.name,
            descriptor.risk_level,
            ", ".join(descriptor.tags),
        )

    console.print(table)


def _task_list_table(supervisor: TaskSupervisor) -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Capability")
    table.add_column("Attempts")

    for task in supervisor.list_tasks():
        table.add_row(
            task.task_id[:8] + "…",
            task.name,
            task.status,
            task.capability,
            _attempts_display(task.attempt, task.max_retries),
        )

    console.print(table)


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

    workflow_parser = subparsers.add_parser("workflow", help="Run orchestrated workflows.")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", required=True)
    wf_run = workflow_subparsers.add_parser("run", help="Execute a workflow file.")
    wf_run.add_argument("workflow_file", help="Path to a YAML or JSON workflow file.")

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
        _run_panel(task)
        return 0

    if args.command == "capability" and args.capability_command == "list":
        _capability_list_table(registry)
        return 0

    if args.command == "task" and args.task_command == "list":
        _task_list_table(supervisor)
        return 0

    if args.command == "workflow" and args.workflow_command == "run":
        raw = _load_yaml_or_json(args.workflow_file)
        goal = WorkflowGoal(goal=raw["goal"], capabilities=raw.get("capabilities", []))
        steps = [
            PlanStep(name=s["name"], capability=s["capability"], input_hint=s.get("input", {}))
            for s in raw.get("steps", [])
        ]
        orchestrator = WorkflowOrchestrator(
            planner=LinearPlanner(steps=steps),
            worker=PassthroughWorker(),
            validator=PassthroughValidator(),
            supervisor=supervisor,
        )
        result = orchestrator.run(goal)
        _workflow_result_panel(result)
        return 0

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
