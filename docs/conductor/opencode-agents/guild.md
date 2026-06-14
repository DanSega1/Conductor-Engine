# Guild Agent

**Config:** `.opencode/agents/guild/guild.json`
**Engine ref:** `docs/conductor/roadmap.md#phase-6--guild-layer`
**Priority:** 12 (Phase 6 — planned)
**Role:** Cross-project failure knowledge sharing.

## Purpose

The guild layer is a structured knowledge store where workers publish what they learned from hard tasks, failure patterns, and edge cases. Other instances of the same role can discover and apply that knowledge. Guild knowledge is structured data (capability + error fingerprint → resolution hint), not LLM embeddings — it works without a model in the loop.

## Invariants

- Knowledge is organized by (capability + error fingerprint) key → resolution hint.
- Role-scoped: a worker role in Project A can learn from a worker role in Project B.
- Role isolation: planner knowledge does not mix with worker knowledge.
- Opt-in per deployment — a deployment handling sensitive data can operate fully isolated.
- Guild knowledge is structured data, not LLM embeddings.

## Subagents

| Subagent | Purpose |
|---|---|
| failure-knowledge-base | Stores failure fingerprints from tasks that failed after max retries. Keyed by (capability + error_type + input_fingerprint). |
| peer-suggestions | Checks guild KB before task execution. Returns resolution hints as input adjustment suggestions. |
| role-knowledge | Role-scoped knowledge sharing. Query failures for the same role+capability across projects. |

## Execution flow

```
Task failure after max retries:
  → guild.failure-knowledge-base.store(failure_context)
  → key = hash(capability + error_type + input_fingerprint)

Before task execution:
  → guild.peer-suggestions.check(input_fingerprint)
  → if match: return resolution_hint as input_adjustment suggestion
  → planner/worker may incorporate the hint or ignore it

Across projects:
  → worker in Project A reports failure for capability X
  → worker in Project B queries guild for capability X failures
  → guild.role-knowledge returns: {error_class, resolved_input_adjustments, confidence}
```

## Knowledge schema

```
Key: hash(capability + error_type + input_fingerprint_prefix)
Value:
  error_message: str
  resolution_hint: str | null
  count: int
  first_seen: datetime
  last_seen: datetime
  role: str        # planner, worker, validator
  project: str     # originating project
```

## When to use

- In deployments with multiple projects sharing the same capabilities
- When transient failures repeat across different contexts (same capability, same error pattern)
- For learning systems that improve over time without human intervention
- Opt-out per deployment for sensitive/isolated environments
