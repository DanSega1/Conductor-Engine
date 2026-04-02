"""Demo: WorkflowOrchestrator end-to-end with the echo capability.

Run with:
    python examples/workflow-echo.py
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from engine.interfaces.workflow import PlanStep, WorkflowGoal
from engine.loader import load_capabilities
from engine.runtime.store import LocalTaskStore
from engine.supervisor.service import TaskSupervisor
from engine.workflow.agents import LinearPlanner, PassthroughValidator, PassthroughWorker
from engine.workflow.orchestrator import WorkflowOrchestrator

console = Console()


def main() -> None:
    steps = [
        PlanStep(name="echo-hello", capability="echo", input_hint={"message": "hello from workflow"}),
        PlanStep(name="echo-world", capability="echo", input_hint={"message": "world"}),
    ]
    goal = WorkflowGoal(goal="Echo two messages in sequence", capabilities=["echo"])

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalTaskStore(Path(tmp) / "tasks.json")
        registry = load_capabilities()
        supervisor = TaskSupervisor(registry=registry, store=store, workdir=Path(tmp))

        orchestrator = WorkflowOrchestrator(
            planner=LinearPlanner(steps=steps),
            worker=PassthroughWorker(),
            validator=PassthroughValidator(),
            supervisor=supervisor,
        )

        result = orchestrator.run(goal)
        _print_result(result)


def _print_result(result) -> None:
    completed = result.status.value == "completed"
    border = "green" if completed else "red"
    status_icon = "✓ completed" if completed else f"✗ {result.status.value}"

    summary = Table.grid(padding=(0, 2))
    summary.add_column()
    summary.add_column()
    summary.add_row(Text("goal", style="bold"), result.goal)
    summary.add_row(
        Text("status", style="bold"),
        Text(status_icon, style="green" if completed else "red"),
    )
    summary.add_row(Text("steps", style="bold"), str(len(result.records)))

    console.print(
        Panel(summary, title="Workflow Result", border_style=border, expand=False, padding=(0, 2))
    )
    console.print()

    for i, record in enumerate(result.records, start=1):
        output_str = (
            json.dumps(record.result.output, ensure_ascii=False)
            if record.result and record.result.output is not None
            else "—"
        )
        step_status = record.status.value

        step_table = Table.grid(padding=(0, 2))
        step_table.add_column(min_width=12)
        step_table.add_column()
        step_table.add_row(Text("capability", style="bold"), record.capability)
        step_table.add_row(
            Text("status", style="bold"),
            Text(step_status, style="green" if step_status == "completed" else "red"),
        )
        step_table.add_row(Text("output", style="bold"), output_str)

        console.print(f"[bold]Step {i}: {record.name}[/bold]")
        console.print(step_table)
        console.print()


if __name__ == "__main__":
    main()
