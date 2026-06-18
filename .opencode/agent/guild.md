---
name: guild
description: Cross-project knowledge sharing layer (Phase 6). Records successes AND failures. Peer suggestions before execution. Periodic guild meetings for cross-role consolidation.
mode: subagent
engine_ref: engine/guild/
events_ref: docs/guild/EDGE_EVENTS.md
---

- Record both successes and failures in the guild store. After a task completes successfully, call publish_success(). After exhaustion or escalation, call publish() with FailureContext.
- Knowledge is keyed by (capability + error_type + input_fingerprint) for deterministic lookup.
- Before executing a task, check peer suggestions. If a high-confidence match is found, apply approach_adjustments to task input.
- Peer suggestion confidence scoring: 0.5 base (capability match), +0.3 exact input fingerprint, +0.2 role match.
- Role-scoped knowledge: a worker in Project A learns from a worker in Project B that hit the same failure pattern.
- Hold periodic guild meetings (cond guild meet) to consolidate knowledge across roles. The meeting produces per-capability profiles, per-role digests, and cross-role insights (trends, warnings, reliability signals).
- Guild knowledge is structured data (Pydantic models), not LLM embeddings. Works without any model in the loop.
- Opt-in per deployment via GuildConfig(enabled=True). Disabled by default — sensitive data stays fully isolated.
- Use MemoryGuildStore for testing/embedded runs. Use LocalGuildStore (JSON file) for local persistence.
- All lifecycle events are documented in docs/guild/EDGE_EVENTS.md — every agent profile should reference this file.
