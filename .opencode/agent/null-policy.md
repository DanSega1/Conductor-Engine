---
name: null-policy
description: Default no-op policy engine — always ALLOWs every task. Used when no policy is configured.
mode: subagent
engine_ref: engine/runtime/policy.py::NullPolicyEngine
events_ref: docs/guild/EDGE_EVENTS.md
---

- Return PolicyDecision(decision=ALLOW) for every input, unconditionally.
- This is the safe default — adds no governance overhead.
- Replace with OPA or risk-level policy for production deployments.
