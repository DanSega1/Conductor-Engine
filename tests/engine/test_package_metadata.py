"""Packaging metadata checks for non-code distribution assets."""

from __future__ import annotations

from pathlib import Path
import tomllib


def test_pyproject_installs_manpage_to_standard_location() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text())

    data_files = config["tool"]["setuptools"]["data-files"]

    assert data_files["share/man/man1"] == ["docs/man/cond.1"]


def test_cond_manpage_source_exists() -> None:
    manpage = Path("docs/man/cond.1")

    assert manpage.exists()
    assert ".TH COND 1" in manpage.read_text()
