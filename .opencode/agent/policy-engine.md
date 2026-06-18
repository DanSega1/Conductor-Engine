---
name: policy-engine
description: Evaluates tasks before capability execution. Implements PolicyEngine Protocol. Can return ALLOW, DENY, or REQUIRE_APPROVAL.
mode: subagent
engine_ref: engine/interfaces/policy.py::PolicyEngine
events_ref: docs/guild/EDGE_EVENTS.md
---

- Receive a deep copy of the TaskRecord and a PolicyContext (capability descriptor + workdir).
- Return a PolicyDecision with decision (ALLOW, DENY, REQUIRE_APPROVAL), reason (str), and metadata (dict).
- DENY transitions task to POLICY_DENIED. REQUIRE_APPROVAL transitions to AWAITING_APPROVAL.
- ALLOW leaves the task in PENDING for execution to proceed.
- Policy is evaluated before capability execution, not before submission.
- The require_approval capability descriptor flag is checked BEFORE the policy engine (in the supervisor).
- Stamp audit entries with policy_engine (class name) and decision_type in metadata.
