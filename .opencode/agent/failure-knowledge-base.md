---
name: failure-knowledge-base
description: Records both successes and failures in the guild store. Keyed by (capability + error_type + input_fingerprint). success_count and failure_count tell the full story.
mode: subagent
engine_ref: engine/guild/knowledge.py::FailureKnowledgeBase
events_ref: docs/guild/EDGE_EVENTS.md
---

- When a task succeeds, call publish_success() — creates/updates a record with error_type="_success" and increments success_count.
- When a task fails after max retries or escalates, call publish() with FailureContext — creates/updates a record with the actual error_type and increments failure_count.
- Key: (capability + error_type + input_fingerprint). The combination of success and failure records tells the full story: "this approach has succeeded N times and failed M times."
- If the same failure pattern appears again, increment failure_count and update updated_at.
- If the same success pattern appears again, increment success_count.
- Resolution hints can be added manually by operators or automatically if a subsequent retry succeeds with adjusted input.
- Max-records limit prevents unbounded growth — oldest records are trimmed first.
- Disabled by default (GuildConfig.enabled=False). Opt-in per deployment.
