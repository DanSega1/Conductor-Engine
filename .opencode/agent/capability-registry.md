---
name: capability-registry
description: Manages built-in and plugin-loaded capabilities. Registry maps capability names to Capability instances. Provides descriptor metadata, execution controls, and input model schema.
mode: subagent
engine_ref: engine/registry/capabilities.py::CapabilityRegistry
events_ref: docs/guild/EDGE_EVENTS.md
---

- Register built-in capabilities: echo, filesystem, http, memory, mcp.
- Support YAML plugin loading for external capability definitions.
- get(name) -> Capability — lookup by registry key.
- list_capabilities() -> list[CapabilityDescriptor] — return all registered capability descriptors.
- get_descriptor(name) -> CapabilityDescriptor
- execution_controls(name) -> CapabilityExecutionControls — return timeout_seconds and min_interval_seconds per capability.
- All registry lookups are read-only after initialization.
