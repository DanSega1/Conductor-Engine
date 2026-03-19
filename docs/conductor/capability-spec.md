# Capability Spec

## Goal

Capabilities are the pluggable execution surface of Conductor Engine. The engine itself stays generic; all side effects flow through registered capabilities.

## Runtime Contract

Each capability exposes:

- `descriptor.name`
- `descriptor.description`
- `descriptor.risk_level`
- `descriptor.tags`
- `validate_input(payload)`
- `execute(payload, context)`

## Execution Rules

- Capability input validation happens before a task leaves `pending`.
- Capability execution receives a `CapabilityContext` containing `task_id`, `task_name`, and `workdir`.
- Capability results are normalized into `CapabilityResult` so the supervisor can persist them consistently.

## Dynamic Loading

Capabilities can be registered in two ways:

1. Built-ins loaded automatically by the runtime
2. Plugin classes loaded from YAML using Python import paths

Example:

```yaml
include_builtins: true
capabilities:
  - import_path: my_package.capabilities:CustomCapability
    config:
      api_base_url: https://example.internal
```

## Built-In Examples

- `echo`: smoke tests and contract verification
- `filesystem`: local file reads/writes under a configured root
- `http`: simple outbound GET/POST calls
