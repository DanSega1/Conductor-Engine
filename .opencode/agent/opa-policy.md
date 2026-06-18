---
name: opa-policy
description: Open Policy Agent (OPA) integration. Evaluates task/capability/input against external Rego policies.
mode: subagent
engine_ref: engine/runtime/policy.py::OPAPolicyEngine
events_ref: docs/guild/EDGE_EVENTS.md
---

- Query an external OPA server with the task record, capability descriptor, and input as the document.
- Return the OPA decision as a PolicyDecision (ALLOW, DENY, REQUIRE_APPROVAL).
- Include the OPA decision reason and full OPA result in metadata.
- If OPA is unreachable, fail closed (DENY with reason).
