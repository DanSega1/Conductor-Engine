---
name: echo-capability
description: Echo capability — returns the input unchanged as output. Used for testing and smoke tests.
mode: subagent
engine_ref: engine/capabilities/echo.py::EchoCapability
events_ref: docs/guild/EDGE_EVENTS.md
risk_level: low
---

- Receives arbitrary input and returns it as output identically.
- No side effects. Stateless. Safe for any caller.
- Useful for pipeline smoke tests and verifying supervisor flow without real execution.
