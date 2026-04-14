"""Minimal CLI for the Conductor Engine."""

from __future__ import annotations

import argparse
from importlib.metadata import version as _pkg_version
import json
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import yaml

from engine.interfaces.task import TaskRecord, TaskStatus, TaskSubmission
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
        "summary": "List, inspect, and operate on stored tasks.",
        "usage": (
            "cond task list [--limit N] [--offset N] [--status STATUS]\n"
            "cond task show <task-id-or-prefix>\n"
            "cond task approve <task-id-or-prefix> [--actor NAME] [--no-run]\n"
            "cond task cancel <task-id-or-prefix> [--actor NAME] [--reason TEXT]"
        ),
        "details": (
            "Task inspection reads from the local store and accepts unique task-id prefixes from "
            "the list view. Detailed task output includes workflow linkage, timestamps, result data, "
            "and the audit trail when present."
        ),
        "example": "cond task list --status awaiting_approval --limit 10",
    },
    "health": {
        "summary": "Run runtime health checks for CLI-facing components.",
        "usage": "cond health",
        "details": (
            "Calls health_check() on the registry, store, queue, event bus, policy engine, and "
            "supervisor. Exit code is 0 when healthy and 1 when issues are detected."
        ),
        "example": "cond --store /tmp/tasks.json health",
    },
}

MAN_PAGE_HINT = "See `man cond` for the static CLI reference."

STATUS_STYLES: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "yellow",
    TaskStatus.RUNNING: "cyan",
    TaskStatus.COMPLETED: "green",
    TaskStatus.FAILED: "red",
    TaskStatus.AWAITING_APPROVAL: "yellow",
    TaskStatus.APPROVED: "green",
    TaskStatus.POLICY_DENIED: "red",
    TaskStatus.CANCELLED: "red",
}

STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "pending",
    TaskStatus.RUNNING: "running",
    TaskStatus.COMPLETED: "completed",
    TaskStatus.FAILED: "failed",
    TaskStatus.AWAITING_APPROVAL: "awaiting approval",
    TaskStatus.APPROVED: "approved",
    TaskStatus.POLICY_DENIED: "policy denied",
    TaskStatus.CANCELLED: "cancelled",
}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("Value must be zero or greater")
    return parsed


def _status_choices() -> list[str]:
    return [status.value for status in TaskStatus]


def _load_yaml_or_json(path: str | Path) -> dict[str, Any]:
    task_path = Path(path)
    raw = task_path.read_text(encoding="utf-8")
    if task_path.suffix == ".json":
        return json.loads(raw)
    return yaml.safe_load(raw)


def _resolve_registry(config_path: str | None, workdir: Path) -> CapabilityRegistry:
    if config_path:
        return load_capabilities(config_path, base_path=workdir)
    if DEFAULT_CONFIG.exists():
        return load_capabilities(DEFAULT_CONFIG, base_path=workdir)
    return load_capabilities(base_path=workdir)


def _format_output(value: Any, *, max_length: int | None = 120) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if max_length is not None and len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _format_block(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True)


def _format_timestamp(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(value)


def _attempts_display(attempt: int, max_retries: int) -> str:
    if max_retries > 0:
        return f"{attempt} / {max_retries + 1}"
    return str(attempt)


def _status_text(status: TaskStatus | str) -> Text:
    status_value = status if isinstance(status, TaskStatus) else TaskStatus(status)
    return Text(STATUS_LABELS[status_value], style=STATUS_STYLES[status_value])


def _status_border_style(status: TaskStatus) -> str:
    return STATUS_STYLES.get(status, "blue")


def _task_id_display(task_id: str) -> str:
    if len(task_id) <= 8:
        return task_id
    return task_id[:8] + "..."


def _task_overview_panel(
    task: TaskRecord,
    *,
    show_identity: bool = False,
    show_timestamps: bool = False,
) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(min_width=10)
    grid.add_column()

    grid.add_row(Text("status", style="bold"), _status_text(task.status))
    if show_identity:
        grid.add_row(Text("task id", style="bold"), task.task_id)
        grid.add_row(Text("workflow", style="bold"), task.workflow_id or "-")
    grid.add_row(Text("capability", style="bold"), task.capability)
    grid.add_row(Text("attempts", style="bold"), _attempts_display(task.attempt, task.max_retries))
    if show_timestamps:
        grid.add_row(Text("created", style="bold"), _format_timestamp(task.created_at))
        grid.add_row(Text("updated", style="bold"), _format_timestamp(task.updated_at))
        if task.archived_at is not None:
            grid.add_row(Text("archived", style="bold"), _format_timestamp(task.archived_at))
    if task.result and task.result.output is not None:
        grid.add_row(Text("output", style="bold"), _format_output(task.result.output))
    if task.result and task.result.error:
        grid.add_row(Text("error", style="bold"), task.result.error)

    return Panel(grid, title=task.name, border_style=_status_border_style(task.status))


def _run_panel(task: TaskRecord) -> None:
    console.print(_task_overview_panel(task))


def _workflow_result_panel(result: WorkflowResult) -> None:
    is_success = result.status == "completed"
    status_text = Text()
    if is_success:
        status_text.append("completed", style="green")
    else:
        status_text.append(str(result.status), style="red")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(min_width=10)
    grid.add_column()

    grid.add_row(Text("goal", style="bold"), result.goal)
    grid.add_row(Text("status", style="bold"), status_text)
    grid.add_row(Text("steps", style="bold"), str(len(result.records)))
    grid.add_row(Text("workflow", style="bold"), result.workflow_id)

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


def _task_list_table(
    supervisor: TaskSupervisor,
    *,
    limit: int | None = None,
    offset: int = 0,
    status: str | None = None,
) -> None:
    tasks = supervisor.list_tasks(limit=limit, offset=offset, status=status)
    matched_total = len(supervisor.list_tasks(status=status))

    summary = Table.grid(padding=(0, 2))
    summary.add_column(min_width=10)
    summary.add_column()
    summary.add_row(Text("matched", style="bold"), str(matched_total))
    summary.add_row(Text("shown", style="bold"), str(len(tasks)))
    summary.add_row(Text("offset", style="bold"), str(offset))
    summary.add_row(Text("limit", style="bold"), str(limit) if limit is not None else "-")
    summary.add_row(Text("status", style="bold"), status or "all")
    console.print(Panel(summary, title="task list", border_style="blue"))

    if not tasks:
        console.print(Panel("No tasks matched the current filters.", border_style="yellow"))
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Capability")
    table.add_column("Attempts")

    for task in tasks:
        table.add_row(
            _task_id_display(task.task_id),
            task.name,
            _status_text(task.status),
            task.capability,
            _attempts_display(task.attempt, task.max_retries),
        )

    console.print(table)


def _task_detail(task: TaskRecord) -> None:
    console.print(_task_overview_panel(task, show_identity=True, show_timestamps=True))

    console.print(Panel(_format_block(task.input), title="input", border_style="cyan"))

    if task.metadata:
        console.print(Panel(_format_block(task.metadata), title="metadata", border_style="blue"))

    if task.result and task.result.output is not None:
        console.print(Panel(_format_block(task.result.output), title="output", border_style="green"))

    if task.result and task.result.metadata:
        console.print(
            Panel(_format_block(task.result.metadata), title="result metadata", border_style="cyan")
        )

    if task.result and task.result.error:
        console.print(Panel(task.result.error, title="error", border_style="red"))

    if not task.audit_trail:
        console.print(Panel("No audit entries recorded.", title="audit trail", border_style="yellow"))
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
    table.add_column("Time")
    table.add_column("Actor")
    table.add_column("Action")
    table.add_column("Transition")
    table.add_column("Metadata")

    for entry in task.audit_trail:
        from_status = entry.from_status.value if entry.from_status is not None else "-"
        to_status = entry.to_status.value if entry.to_status is not None else "-"
        transition = f"{from_status} -> {to_status}"
        metadata = _format_output(entry.metadata, max_length=80) or "-"
        table.add_row(
            _format_timestamp(entry.timestamp),
            entry.actor,
            entry.action,
            transition,
            metadata,
        )

    console.print(Panel(table, title="audit trail", border_style="blue"))


def _component_issues(component: object) -> list[str]:
    checker = getattr(component, "health_check", None)
    if checker is None:
        return []
    return list(checker())


def _health_panel(registry: CapabilityRegistry, store: LocalTaskStore, supervisor: TaskSupervisor) -> int:
    components = [
        ("registry", registry, f"{len(registry.names())} capabilities loaded"),
        ("task_store", store, str(store.path)),
        ("queue", supervisor.queue, f"{len(supervisor.queue.list())} queued"),
        ("event_bus", supervisor._bus, type(supervisor._bus).__name__),
        ("policy", supervisor._policy, type(supervisor._policy).__name__),
        ("supervisor", supervisor, supervisor.workdir),
    ]

    unhealthy = False
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
    table.add_column("Component")
    table.add_column("Status")
    table.add_column("Details")

    issue_rows: list[tuple[str, str]] = []
    for name, component, detail in components:
        issues = _component_issues(component)
        if issues:
            unhealthy = True
            table.add_row(name, Text("issues found", style="red"), detail)
            for issue in issues:
                issue_rows.append((name, issue))
        else:
            table.add_row(name, Text("healthy", style="green"), detail)

    console.print(Panel(table, title="cond health", border_style="red" if unhealthy else "green"))

    if issue_rows:
        issue_table = Table(show_header=True, header_style="bold", box=None, pad_edge=True)
        issue_table.add_column("Component")
        issue_table.add_column("Issue")
        for name, issue in issue_rows:
            issue_table.add_row(name, issue)
        console.print(issue_table)
        return 1

    console.print(Panel("All CLI-facing components passed health_check().", border_style="green"))
    return 0


def _resolve_task(supervisor: TaskSupervisor, task_id_or_prefix: str) -> TaskRecord:
    try:
        return supervisor.get_task(task_id_or_prefix)
    except ValueError:
        matches = [task for task in supervisor.list_tasks() if task.task_id.startswith(task_id_or_prefix)]
        if not matches:
            raise ValueError(f"Task '{task_id_or_prefix}' was not found") from None
        if len(matches) > 1:
            raise ValueError(
                f"Task id prefix '{task_id_or_prefix}' is ambiguous; provide more characters"
            ) from None
        return supervisor.get_task(matches[0].task_id)


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

    task_list = task_subparsers.add_parser("list", help="List tasks from the local store.")
    task_list.add_argument("--limit", type=_positive_int, default=None, help="Maximum tasks to show.")
    task_list.add_argument("--offset", type=_non_negative_int, default=0, help="Tasks to skip before listing.")
    task_list.add_argument(
        "--status",
        choices=_status_choices(),
        default=None,
        help="Filter tasks by status.",
    )

    task_show = task_subparsers.add_parser("show", help="Show one task in detail.")
    task_show.add_argument("task_id", help="Full task id or unique prefix.")

    task_approve = task_subparsers.add_parser("approve", help="Approve a task awaiting approval.")
    task_approve.add_argument("task_id", help="Full task id or unique prefix.")
    task_approve.add_argument("--actor", default="cli", help="Actor name recorded in the audit trail.")
    task_approve.add_argument(
        "--no-run",
        action="store_true",
        help="Mark the task approved without executing it immediately.",
    )

    task_cancel = task_subparsers.add_parser("cancel", help="Cancel a task awaiting approval.")
    task_cancel.add_argument("task_id", help="Full task id or unique prefix.")
    task_cancel.add_argument("--actor", default="cli", help="Actor name recorded in the audit trail.")
    task_cancel.add_argument("--reason", default=None, help="Optional cancellation reason.")

    workflow_parser = subparsers.add_parser("workflow", help="Run orchestrated workflows.")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", required=True)
    wf_run = workflow_subparsers.add_parser("run", help="Execute a workflow file.")
    wf_run.add_argument("workflow_file", help="Path to a YAML or JSON workflow file.")

    subparsers.add_parser("health", help="Run CLI-facing health checks.")

    help_parser = subparsers.add_parser("help", help="Show offline help topics.")
    help_parser.add_argument("topic", nargs="?", help="Optional command or capability topic.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
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
            _task_list_table(
                supervisor,
                limit=args.limit,
                offset=args.offset,
                status=args.status,
            )
            return 0

        if args.command == "task" and args.task_command == "show":
            task = _resolve_task(supervisor, args.task_id)
            _task_detail(task)
            return 0

        if args.command == "task" and args.task_command == "approve":
            task = _resolve_task(supervisor, args.task_id)
            updated = supervisor.approve_task(task.task_id, actor=args.actor, run=not args.no_run)
            _task_detail(updated)
            return 0

        if args.command == "task" and args.task_command == "cancel":
            task = _resolve_task(supervisor, args.task_id)
            updated = supervisor.cancel_task(task.task_id, actor=args.actor, reason=args.reason)
            _task_detail(updated)
            return 0

        if args.command == "workflow" and args.workflow_command == "run":
            raw = _load_yaml_or_json(args.workflow_file)
            goal = WorkflowGoal(goal=raw["goal"], capabilities=raw.get("capabilities", []))
            steps = [
                PlanStep(
                    name=step["name"],
                    capability=step["capability"],
                    input_hint=step.get("input", {}),
                    parallel_group=step.get("parallel_group"),
                )
                for step in raw.get("steps", [])
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

        if args.command == "health":
            return _health_panel(registry, store, supervisor)

        if args.command == "help":
            return _render_help(args.topic, registry)

        parser.error("Unsupported command")
        return 2
    except (FileNotFoundError, KeyError, ValueError, ValidationError, json.JSONDecodeError, yaml.YAMLError) as exc:
        err_console.print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
