# Policy Engine Agent

**Config:** `.opencode/agents/policy/policy.json`
**Engine ref:** `engine/interfaces/policy.py::PolicyEngine`
**Priority:** 6
**Role:** Evaluates tasks before capability execution.

## Purpose

The policy engine receives a deep copy of the `TaskRecord` and a `PolicyContext` (capability descriptor + workdir) and returns a `PolicyDecision` — ALLOW, DENY, or REQUIRE_APPROVAL. Policy is evaluated in the supervisor **before** capability execution but **after** the `require_approval` descriptor flag check.

## Invariants

- Policy is evaluated before capability execution, not before submission.
- The `require_approval` capability descriptor flag is checked BEFORE the policy engine.
- DENY → task transitions to POLICY_DENIED.
- REQUIRE_APPROVAL → task transitions to AWAITING_APPROVAL.
- ALLOW → task stays in PENDING for execution to proceed.
- Every evaluation stamps policy_engine (class name) and decision_type in audit metadata.

## Subagents

| Subagent | Engine ref | Purpose |
|---|---|---|
| null-policy | `engine/runtime/policy.py::NullPolicyEngine` | Always ALLOW. Safe default when no policy is configured. |
| opa-policy | `engine/runtime/policy.py::OPAPolicyEngine` | Queries external OPA server with Rego policies. Fail closed on unreachable. |
| risk-level-policy | `engine/runtime/policy.py::RiskLevelPolicyEngine` | Deny/require_approval based on capability risk level threshold. |

## Policy decision flow

```
supervisor.run_task(task)
  → if task.status == PENDING:
      if capability.descriptor.require_approval:
        → AWAITING_APPROVAL (BEFORE policy engine)
      else:
        policy_engine.evaluate(task, PolicyContext)
        → if DENY:           POLICY_DENIED
        → if REQUIRE_APPROVAL: AWAITING_APPROVAL
        → if ALLOW:          proceed to execute
```

## Subagent behavior

| Subagent | ALLOW | DENY | REQUIRE_APPROVAL |
|---|---|---|---|
| null-policy | always | never | never |
| opa-policy | OPA allows | OPA denies | OPA requires |
| risk-level-policy | risk ≤ threshold | risk > deny_threshold | risk between warning and deny |

## When to use

- null-policy: development, testing, minimal deployments
- risk-level-policy: when capability risk levels are configured and need automated enforcement
- opa-policy: production with externalized policy definitions in Rego
