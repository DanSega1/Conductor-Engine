# Examples

Runnable examples for Conductor Engine tasks, workflows, and capability config files.

| File | Description | Run |
|---|---|---|
| `examples/echo.yaml` | Minimal echo smoke test for validating the CLI and task execution path. | `cond run examples/echo.yaml` |
| `examples/write-file.yaml` | Writes a text file through the filesystem capability. | `cond run examples/write-file.yaml` |
| `examples/read-file.yaml` | Reads the file created by `write-file.yaml`. | `cond run examples/read-file.yaml` |
| `examples/retry.yaml` | Exercises retry behavior against a failing HTTP task. | `cond run examples/retry.yaml` |
| `examples/workflow-echo.yaml` | Runs a two-step workflow through the workflow orchestrator. | `cond workflow run examples/workflow-echo.yaml` |
| `examples/workflow-parallel.yaml` | Fans out two adjacent `parallel_group` echo steps, then crosses a sequential filesystem barrier step that writes `examples/output/parallel-barrier.txt`. | `cond workflow run examples/workflow-parallel.yaml` |
| `examples/capability-execution-controls.yaml` | Demonstrates top-level `execution_controls` for built-in capabilities. Pass it through the CLI's global `--config` flag. | `cond --config examples/capability-execution-controls.yaml run examples/echo.yaml` |
| `examples/workflow-echo.py` | Python entry point for the same workflow flow without the CLI. | `python examples/workflow-echo.py` |

`examples/capability-execution-controls.yaml` is a config file, not a task file. Use it with any normal `cond` command via the global `--config` flag.

The timeout values in that config demonstrate the current Phase 3 soft in-process timeout wrapper: the supervisor can mark a task failed after the deadline, but arbitrary in-flight work is not forcibly terminated.
