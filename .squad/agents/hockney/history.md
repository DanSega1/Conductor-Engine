# Hockney — History

## Core Context

**Project:** Conductor-Engine — Python 3.12+ orchestration runtime (Pydantic v2, httpx, pyyaml)
**Owner:** Dan
**Role:** CLI & Integration Dev

## Learnings

### 2026-03-31 — Project kickoff
- `cli/cond.py` is the entry point; registered as `cond = "cli.cond:main"` in pyproject.toml
- Current CLI commands: `capability list`, `run <task.yaml>`, `task list`
- `engine/loader.py` handles YAML task parsing — produces `TaskSubmission` for the supervisor
- Plugin capabilities are declared in `config/conductor.capabilities.yaml` via `import_path`
- The CLI calls the supervisor directly; no REST layer exists yet (deferred to a later phase)
- Task YAML format is documented in `docs/conductor/task-model.md` — follow that schema exactly
- Tests for CLI behavior live in `tests/engine/test_cli.py`

### 2026-03-31 — Rich CLI output (hockney-rich-output)

Built human-friendly CLI output for all three `cond` commands using `rich`.

- Added `rich>=13` to `[project] dependencies` in `pyproject.toml`.
- Added `Console()` (stdout) and `Console(stderr=True)` module-level singletons in `cli/cond.py`.
- Replaced the three `print(_json_dump(...))` calls with dedicated render helpers:
  - `_run_panel(task)` — renders a `Panel` titled with the task name; status row uses `rich.text.Text` with green/red styling for ✓/✗; attempts line shows `n / max+1` when retries are configured; output/error appended conditionally.
  - `_capability_list_table(registry)` — borderless `Table` with Name, Risk, Tags columns.
  - `_task_list_table(supervisor)` — borderless `Table` with ID (8-char prefix + …), Name, Status, Capability, Attempts.
- `_json_dump` was kept intact (used by tests and potentially other callers).
- `_format_output` helper handles str vs dict/list, compacts JSON, truncates at 120 chars.
- `_attempts_display` helper encapsulates `attempt` vs `attempt / max_retries+1` logic.
- No new CLI flags added; scope kept minimal per the task spec.

### 2026-04-01 — WorkflowOrchestrator demo (workflow-echo)

Created `try-it/workflow-echo.py` and `engine/workflow/agents.py`.

- `engine/workflow/agents.py` didn't exist; created it with `LinearPlanner`, `PassthroughWorker`, `PassthroughValidator` — concrete, zero-dependency implementations of the three `engine.interfaces.workflow` Protocol roles.
- `LinearPlanner` takes a pre-built `list[PlanStep]` at construction and returns it verbatim; cleanest pattern for deterministic demos and tests.
- `PassthroughWorker.work()` maps `step.input_hint` directly to `TaskSubmission.input`; the hint/input distinction is advisory — a real worker would enrich or transform it.
- `PassthroughValidator` always returns `ValidationResponse(passed=True)` — null-object pattern for workflows that don't need outcome assessment.
- Rich panel pattern: `Table.grid(padding=(0, 2))` with `Text("label", style="bold")` per row avoids the dark-background column-highlight bug.
- `LocalTaskStore` auto-creates its parent dir; `Path(tmp) / "tasks.json"` inside `tempfile.TemporaryDirectory` gives teardown-safe temp persistence for demos.

### 2026-04-01 — `cond workflow run <file.yaml>` (Phase 2 — Step 4)

Added `workflow run` subcommand to `cli/cond.py`.

- Added nested subparsers under `workflow` with `dest="workflow_command"` — mirrors the existing `capability`/`task` pattern.
- New imports: `PlanStep`, `WorkflowGoal`, `WorkflowResult` from `engine.interfaces.workflow`; `LinearPlanner`, `PassthroughValidator`, `PassthroughWorker` from `engine.workflow.agents`; `WorkflowOrchestrator` from `engine.workflow.orchestrator`.
- `_workflow_result_panel(result)` prints a summary Panel (goal/status/step count) then delegates each `TaskRecord` to the existing `_run_panel` — zero duplication.
- `Table.grid` columns must NOT use `style=` parameter (causes black rectangles in Rich); labels use `Text("label", style="bold")` instead.
- Handler converts the raw YAML `steps` list to `PlanStep` objects using `input_hint=s.get("input", {})` before constructing `LinearPlanner`.
