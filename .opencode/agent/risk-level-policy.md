---
name: risk-level-policy
description: Risk-level-based policy engine. Evaluates capability risk level against configured thresholds.
mode: subagent
engine_ref: engine/runtime/policy.py::RiskLevelPolicyEngine
events_ref: docs/guild/EDGE_EVENTS.md
---

- Read the capability's risk_level from its descriptor (low, medium, high, critical).
- Compare against a configured threshold (e.g., deny above medium).
- Return ALLOW for permitted levels, REQUIRE_APPROVAL for warning levels, DENY for blocked levels.
- Configuration is set at engine level, not per-task.
