# Examples

Runnable examples for Conductor Engine tasks and workflows.

| File | Description | Run |
|---|---|---|
| `examples/echo.yaml` | Minimal echo smoke test for validating the CLI and task execution path. | `cond run examples/echo.yaml` |
| `examples/write-file.yaml` | Writes a text file through the filesystem capability. | `cond run examples/write-file.yaml` |
| `examples/read-file.yaml` | Reads the file created by `write-file.yaml`. | `cond run examples/read-file.yaml` |
| `examples/retry.yaml` | Exercises retry behavior against a failing HTTP task. | `cond run examples/retry.yaml` |
| `examples/workflow-echo.yaml` | Runs a two-step workflow through the workflow orchestrator. | `cond workflow run examples/workflow-echo.yaml` |
| `examples/workflow-echo.py` | Python entry point for the same workflow flow without the CLI. | `python examples/workflow-echo.py` |
