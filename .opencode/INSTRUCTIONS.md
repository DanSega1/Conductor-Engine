# Conductor Engine Instructions

## Agent Delegation
- The Supervisor agent owns all agent delegation. No agent calls capabilities directly — always route through the Supervisor (matches engine invariant: supervisor is the only path through which a capability executes).

## Planner
- Planner agents break goals into ordered PlanSteps. They never execute — they return a plan for the orchestrator to dispatch.

## Worker
- Worker agents turn PlanSteps into TaskSubmissions. They call capabilities via the Supervisor, never directly.

## Validator
- Validator agents assess completed workflow results (pass/fail verdict). They never modify tasks.

## Policy
- Policy engines evaluate before capability execution (DENY / ALLOW / REQUIRE_APPROVAL). They operate before guardrails in the submission gate.

## Guardrails
- Guardrails validate input schema and path safety before any task leaves PENDING.

## Store
- Store agents persist TaskRecords at every state transition. Reads return deep copies.

## Retry
- Retry strategies decide whether to retry after a capability failure. They never execute tasks.

## Escalation
- Escalated is terminal — once a task reaches ESCALATED, it cannot return to RUNNING.

## Guild
- Guild agents share failure fingerprints and resolution hints across projects (Phase 6).

## Control Plane
- Control-plane agents expose versioned HTTP API surfaces — they consume the engine, they do not replace it.

## Scheduler
- Scheduler agents poll cron/webhook triggers and submit dispatches through the supervisor path.
