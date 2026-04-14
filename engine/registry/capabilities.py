"""Capability registry for discovery and lookup."""

from __future__ import annotations

from engine.interfaces.capability import (
    Capability,
    CapabilityDescriptor,
    CapabilityExecutionControls,
)


class CapabilityRegistry:
    """In-memory registry of capability implementations."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._execution_controls: dict[str, CapabilityExecutionControls] = {}

    def register(
        self,
        capability: Capability,
        *,
        execution_controls: CapabilityExecutionControls | None = None,
    ) -> None:
        name = capability.descriptor.name
        if name in self._capabilities:
            raise ValueError(f"Capability '{name}' is already registered")
        self._capabilities[name] = capability
        if execution_controls is not None:
            self._execution_controls[name] = execution_controls.model_copy(deep=True)

    def get(self, name: str) -> Capability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise KeyError(f"Capability '{name}' is not registered") from exc

    def list(self) -> list[CapabilityDescriptor]:
        return [self._capabilities[name].descriptor for name in sorted(self._capabilities)]

    def names(self) -> list[str]:
        return [descriptor.name for descriptor in self.list()]

    def set_execution_controls(
        self,
        name: str,
        controls: CapabilityExecutionControls,
    ) -> None:
        if name not in self._capabilities:
            raise ValueError(f"Capability '{name}' is not registered")
        self._execution_controls[name] = controls.model_copy(deep=True)

    def execution_controls(self, name: str) -> CapabilityExecutionControls:
        if name not in self._capabilities:
            raise KeyError(f"Capability '{name}' is not registered")
        controls = self._execution_controls.get(name)
        if controls is None:
            return CapabilityExecutionControls()
        return controls.model_copy(deep=True)

    def health_check(self) -> list[str]:
        issues: list[str] = []
        if not self._capabilities:
            issues.append("capability registry has no registered capabilities")
        for name, capability in sorted(self._capabilities.items()):
            descriptor_name = capability.descriptor.name
            if descriptor_name != name:
                issues.append(
                    "capability registry key mismatch: "
                    f"stored as '{name}' but descriptor reports '{descriptor_name}'"
                )
        for name in sorted(self._execution_controls):
            if name not in self._capabilities:
                issues.append(f"execution controls configured for unknown capability '{name}'")
        return issues
