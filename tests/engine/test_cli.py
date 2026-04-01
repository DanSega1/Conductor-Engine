"""CLI smoke tests for `cond`."""

from __future__ import annotations

from pathlib import Path

from cli.cond import main


def test_capability_list_outputs_builtin_capabilities(capsys) -> None:
    exit_code = main(["capability", "list"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "echo" in captured.out
    assert "filesystem" in captured.out
    assert "http" in captured.out


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

    assert exit_code == 0
    assert "completed" in captured.out
    assert "hello from cond" in captured.out
    assert store_file.exists()
