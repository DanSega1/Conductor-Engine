"""Minimal CLI for the Conductor Engine."""

from __future__ import annotations

import argparse
from importlib.metadata import version as _pkg_version
import json
from pathlib import Path
from typing import Any, get_args, get_origin

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

COMMAND_HELP_TOPICS: dict[str, dict[str, str]] = {
    "run": {
        "summary": "Execute a single task definition from YAML or JSON.",
        "usage": "cond run <task-file>",
        "details": (
            "Task files define a name, capability, and input payload. "
            "Use --store to isolate or inspect a specific local task store."
        ),
        "example": (
            "name: Echo smoke test\n"
            "capability: echo\n"
            "input:\n"
            "  message: hello from conductor"
        ),
    },
    "workflow": {
        "summary": "Execute a workflow YAML through the planner/worker/validator path.",
        "usage": "cond workflow run <workflow-file>",
        "details": (
            "Workflow files define a top-level goal and an ordered list of steps. "
            "Each step is converted into a TaskSubmission and executed by the supervisor."
        ),
        "example": (
            "goal: Echo two messages in sequence\n"
            "capabilities:\n"
            "  - echo\n"
            "steps:\n"
            "  - name: echo-hello\n"
            "    capability: echo\n"
            "    input:\n"
            "      message: hello from workflow"
        ),
    },
    "capability": {
        "summary": "Inspect registered capabilities.",
        "usage": "cond capability list",
        "details": "Lists every loaded capability with its risk level and tags.",
        "example": "cond capability list",
    },
    "task": {
        "summary": "Inspect tasks saved in the local JSON task store.",
        "usage": "cond task list",
        "details": (
            "Task history is read from .conductor/tasks.json by default. "
            "Use --store to point at a different local store file."
        ),
        "example": "cond --store /tmp/tasks.json task list",
    },
}

MAN_PAGE_HINT = "See `man cond` for the static CLI reference."


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


def _type_label(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is None:
        if hasattr(annotation, "__name__"):
            return str(annotation.__name__)
        text = str(annotation)
        return text.replace("typing.", "")
    if origin in {list, set, tuple}:
        args = ", ".join(_type_label(arg) for arg in get_args(annotation))
        return f"{origin.__name__}[{args}]"
    if origin is dict:
        args = ", ".join(_type_label(arg) for arg in get_args(annotation))
        return f"dict[{args}]"
    if origin is type(None):
        return "None"
    args = [_type_label(arg) for arg in get_args(annotation)]
    if str(origin).endswith("Literal"):
        return " | ".join(args)
    if str(origin).endswith("Union"):
        return " | ".join(args)
    name = getattr(origin, "__name__", str(origin).replace("typing.", ""))
    return f"{name}[{', '.join(args)}]"


def _example_value(annotation: Any) -> str:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if str(origin).endswith("Literal") and args:
        return repr(args[0])
    if origin in {list, set, tuple}:
        return "[]"
    if origin is dict:
        return "{}"
    if str(origin).endswith("Union"):
        non_none = [arg for arg in args if arg is not type(None)]
        return _example_value(non_none[0]) if non_none else "null"
    if annotation in {str, Any}:
        return "<value>"
    if annotation is int:
        return "0"
    if annotation is float:
        return "0.0"
    if annotation is bool:
        return "false"
    return "<value>"


def _capability_example_yaml(name: str, capability: Any) -> str:
    lines = ["name: Example task", f"capability: {name}", "input:"]
    if capability.input_model is None:
        lines.append("  {}")
        return "\n".join(lines)
    for field_name, field in capability.input_model.model_fields.items():
        lines.append(f"  {field_name}: {_example_value(field.annotation)}")
    return "\n".join(lines)


def _capability_manual(topic: str, registry: CapabilityRegistry) -> bool:
    try:
        capability = registry.get(topic)
    except KeyError:
        return False

    descriptor = capability.descriptor
    summary = Table.grid(padding=(0, 2))
    summary.add_column(min_width=12)
    summary.add_column()
    summary.add_row(Text("name", style="bold"), descriptor.name)
    summary.add_row(Text("risk", style="bold"), descriptor.risk_level)
    summary.add_row(Text("tags", style="bold"), ", ".join(descriptor.tags) or "-")
    summary.add_row(Text("summary", style="bold"), descriptor.description)

    console.print(Panel(summary, title=f"help {topic}", border_style="blue"))

    if capability.input_model is not None:
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
        table.add_column("Field")
        table.add_column("Type")
        table.add_column("Required")
        table.add_column("Default")
        for field_name, field in capability.input_model.model_fields.items():
            default = "-" if field.is_required() else _format_output(field.default)
            table.add_row(
                field_name,
                _type_label(field.annotation),
                "yes" if field.is_required() else "no",
                default,
            )
        console.print(table)

    manual_text = capability.man_page()
    if manual_text:
        console.print(Panel(manual_text, title="details", border_style="cyan"))

    console.print(Panel(_capability_example_yaml(topic, capability), title="example", border_style="green"))
    console.print(Panel(MAN_PAGE_HINT, title="see also", border_style="cyan"))
    return True


def _command_manual(topic: str) -> bool:
    manual = COMMAND_HELP_TOPICS.get(topic)
    if manual is None:
        return False

    summary = Table.grid(padding=(0, 2))
    summary.add_column(min_width=12)
    summary.add_column()
    summary.add_row(Text("topic", style="bold"), topic)
    summary.add_row(Text("usage", style="bold"), manual["usage"])
    summary.add_row(Text("summary", style="bold"), manual["summary"])
    summary.add_row(Text("details", style="bold"), manual["details"])
    console.print(Panel(summary, title=f"help {topic}", border_style="blue"))
    console.print(Panel(manual["example"], title="example", border_style="green"))
    console.print(Panel(MAN_PAGE_HINT, title="see also", border_style="cyan"))
    return True


def _help_index(registry: CapabilityRegistry) -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
    table.add_column("Topic")
    table.add_column("Kind")
    table.add_column("Summary")

    for topic, manual in sorted(COMMAND_HELP_TOPICS.items()):
        table.add_row(topic, "command", manual["summary"])

    for descriptor in registry.list():
        table.add_row(descriptor.name, "capability", descriptor.description)

    console.print(Panel(table, title="cond help", border_style="blue"))
    console.print(Panel(MAN_PAGE_HINT, title="see also", border_style="cyan"))


def _render_help(topic: str | None, registry: CapabilityRegistry) -> int:
    if topic is None:
        _help_index(registry)
        return 0
    if _command_manual(topic):
        return 0
    if _capability_manual(topic, registry):
        return 0
    err_console.print(f"Unknown help topic: {topic}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cond", description="Conductor Engine CLI")
    parser.add_argument(
        "--version",
        action="version",
        version=f"cond {_pkg_version('conductor-engine')}",
    )
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

    help_parser = subparsers.add_parser("help", help="Show offline help topics.")
    help_parser.add_argument("topic", nargs="?", help="Optional command or capability topic.")

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

    if args.command == "help":
        return _render_help(args.topic, registry)

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
