---
name: peer-suggestions
description: Checks the guild before task execution. Returns suggestions from both failure and success patterns. Confidence scoring guides how much to trust each suggestion.
mode: subagent
engine_ref: engine/guild/peer.py::DefaultPeerSuggestionEngine
events_ref: docs/guild/EDGE_EVENTS.md
---

- Before a task executes, compute input_fingerprint and check guild for matching records (both successes and failures).
- For each match, compute a confidence score: 0.5 base (capability match) + 0.3 if input fingerprint matches exactly + 0.2 if role matches.
- Return suggestions sorted by descending confidence. The supervisor applies approach_adjustments from the best match.
- Success records (error_type="_success") indicate approaches that have worked before — their approach_adjustments capture what made them work.
- The suggestion is advisory — the planner or worker can incorporate it or ignore it.
- If no matching pattern, return empty (no suggestion).
- Disabled by default (GuildConfig.enabled=False).
