"""CLI smoke tests for `cond`."""

from __future__ import annotations

import json
from pathlib import Path

from cli.cond import main


def test_capability_list_outputs_builtin_capabilities(capsys) -> None:
    exit_code = main(["capability", "list"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert [item["name"] for item in payload] == ["echo", "filesystem", "http"]


def test_run_executes_task_and_persists_it(tmp_path: Path, capsys) -> None:
    task_file = tmp_path / "task.yaml"
    store_file = tmp_path / "tasks.json"
    task_file.write_text(
        "\n".join(
            [
                "name: Echo from CLI",
                "capability: echo",
                "input:",
                "  message: hello from cond",
            ]
        )
    )

    exit_code = main(["--store", str(store_file), "run", str(task_file)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["result"]["output"] == {"message": "hello from cond"}
    assert store_file.exists()
