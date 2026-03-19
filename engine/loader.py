"""Capability loading helpers for built-ins and plugin configs."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import yaml

from engine.capabilities import EchoCapability, FilesystemCapability, HttpCapability
from engine.interfaces.capability import Capability
from engine.registry.capabilities import CapabilityRegistry


def _import_object(import_path: str) -> type[Capability]:
    module_name, _, attribute = import_path.partition(":")
    if not module_name or not attribute:
        raise ValueError(
            f"Invalid import path '{import_path}'. Expected format 'package.module:ClassName'"
        )

    module = import_module(module_name)
    obj = getattr(module, attribute)
    if not isinstance(obj, type) or not issubclass(obj, Capability):
        raise ValueError(f"Imported object '{import_path}' is not a Capability subclass")
    return obj


def load_builtin_capabilities(base_path: str | Path | None = None) -> CapabilityRegistry:
    """Load the built-in capability set."""
    registry = CapabilityRegistry()
    registry.register(EchoCapability())
    registry.register(FilesystemCapability(base_path=str(Path(base_path or Path.cwd()).resolve())))
    registry.register(HttpCapability())
    return registry


def load_capabilities_from_file(
    path: str | Path,
    *,
    base_path: str | Path | None = None,
) -> CapabilityRegistry:
    """Load built-in and configured capabilities from a YAML definition file."""
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text()) or {}
    include_builtins = data.get("include_builtins", True)
    root = Path(base_path or Path.cwd()).resolve()

    registry = load_builtin_capabilities(root) if include_builtins else CapabilityRegistry()

    for entry in data.get("capabilities", []):
        import_path = entry["import_path"]
        config = dict(entry.get("config", {}))
        if "base_path" in config:
            config["base_path"] = str((config_path.parent / config["base_path"]).resolve())
        capability_class = _import_object(import_path)
        registry.register(capability_class(**config))

    return registry


def load_capabilities(
    config_path: str | Path | None = None,
    *,
    base_path: str | Path | None = None,
) -> CapabilityRegistry:
    """Load capabilities from config when available, otherwise use built-ins."""
    if config_path is None:
        return load_builtin_capabilities(base_path=base_path)

    candidate = Path(config_path)
    if not candidate.exists():
        raise FileNotFoundError(f"Capability config file not found: {candidate}")
    return load_capabilities_from_file(candidate, base_path=base_path)
