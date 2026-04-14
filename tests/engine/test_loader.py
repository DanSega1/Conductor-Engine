"""Tests for dynamic capability loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.loader import load_builtin_capabilities, load_capabilities_from_file


def test_load_builtin_capabilities_includes_expected_defaults(tmp_path: Path) -> None:
    registry = load_builtin_capabilities(base_path=tmp_path)

    assert registry.names() == ["echo", "filesystem", "http"]


def test_load_capabilities_from_file_supports_builtin_toggle(tmp_path: Path) -> None:
    config_path = tmp_path / "capabilities.yaml"
    config_path.write_text("include_builtins: true\ncapabilities: []\n")

    registry = load_capabilities_from_file(config_path, base_path=tmp_path)

    assert "filesystem" in registry.names()


def test_load_capabilities_from_file_rejects_bad_import_path(tmp_path: Path) -> None:
    config_path = tmp_path / "capabilities.yaml"
    config_path.write_text("include_builtins: false\ncapabilities:\n  - import_path: not-valid\n")

    with pytest.raises(ValueError, match="Invalid import path"):
        load_capabilities_from_file(config_path, base_path=tmp_path)


def test_load_capabilities_from_file_applies_execution_controls(tmp_path: Path) -> None:
    config_path = tmp_path / "capabilities.yaml"
    config_path.write_text(
        "\n".join(
            [
                "include_builtins: true",
                "execution_controls:",
                "  http:",
                "    timeout_seconds: 2.5",
                "    min_interval_seconds: 0.1",
                "capabilities: []",
            ]
        )
    )

    registry = load_capabilities_from_file(config_path, base_path=tmp_path)
    controls = registry.execution_controls("http")

    assert controls.timeout_seconds == 2.5
    assert controls.min_interval_seconds == 0.1
