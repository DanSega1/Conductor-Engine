"""Packaging metadata checks for non-code distribution assets."""

from __future__ import annotations

from pathlib import Path
import tomllib


def test_pyproject_installs_manpage_to_standard_location() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text())

    data_files = config["tool"]["setuptools"]["data-files"]

    assert data_files["share/man/man1"] == ["docs/man/cond.1"]


def test_pyproject_requires_python_314_or_newer() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text())

    assert config["project"]["requires-python"] == ">=3.14"


def test_pyproject_declares_python_classifiers_for_pypi_badges() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text())

    classifiers = config["project"]["classifiers"]

    assert "Programming Language :: Python :: 3" in classifiers
    assert "Programming Language :: Python :: 3.14" in classifiers
    assert "Programming Language :: Python :: Implementation :: CPython" in classifiers


def test_cond_manpage_source_exists() -> None:
    manpage = Path("docs/man/cond.1")

    assert manpage.exists()
    assert ".TH COND 1" in manpage.read_text()
