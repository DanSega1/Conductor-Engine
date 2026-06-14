# Capability Registry Agent

**Config:** `.opencode/agents/capability-registry/capability-registry.json`
**Engine ref:** `engine/registry/capabilities.py::CapabilityRegistry`
**Priority:** 5
**Role:** Manages built-in and plugin-loaded capabilities. Registry is read by supervisor for dispatch.

## Purpose

The capability registry maps capability names (strings) to `Capability` instances. It provides descriptor metadata (`CapabilityDescriptor`), execution controls (`CapabilityExecutionControls`), and input model schema for each capability. All registry lookups are read-only after initialization.

## Invariants

- Read-only after initialization. No runtime registration.
- `get(name)` returns the Capability instance for execution dispatch.
- `execution_controls(name)` returns timeout and rate-limit settings.
- Capabilities are stateless — no shared mutable state on the instance.

## Execution contract

```
get(name: str)              → Capability
list_capabilities()         → list[CapabilityDescriptor]
get_descriptor(name: str)   → CapabilityDescriptor
execution_controls(name)    → CapabilityExecutionControls(timeout_seconds, min_interval_seconds)
```

## Registered capabilities

| Name | Module | Risk | require_approval |
|---|---|---|---|
| echo | `engine/capabilities/echo.py` | low | false |
| filesystem | `engine/capabilities/filesystem.py` | high | configurable |
| http | `engine/capabilities/http.py` | medium | false |
| memory | `engine/capabilities/memory.py` | low | false |
| mcp | `engine/capabilities/mcp.py` | medium | false |

## When to use

- Before any capability execution, to resolve the name to an instance
- To discover available capabilities (CLI: `cond capability list`, API: `GET /v1/capabilities`)
- To check execution controls before running a capability
- To load plugin capabilities from YAML configuration
