"""Capability registry for discovery and lookup."""

from __future__ import annotations

from engine.interfaces.capability import Capability, CapabilityDescriptor


class CapabilityRegistry:
    """In-memory registry of capability implementations."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        name = capability.descriptor.name
        if name in self._capabilities:
            raise ValueError(f"Capability '{name}' is already registered")
        self._capabilities[name] = capability

    def get(self, name: str) -> Capability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise KeyError(f"Capability '{name}' is not registered") from exc

    def list(self) -> list[CapabilityDescriptor]:
        return [self._capabilities[name].descriptor for name in sorted(self._capabilities)]

    def names(self) -> list[str]:
        return [descriptor.name for descriptor in self.list()]
