---
name: role-knowledge
description: Role-scoped knowledge sharing — agents of the same role learn from each other across projects. Edge events are the shared vocabulary all roles understand.
mode: subagent
engine_ref: engine/guild/peer.py::DefaultPeerSuggestionEngine
events_ref: docs/guild/EDGE_EVENTS.md
---

- Agents are organized by role (supervisor, planner, worker, validator). Multiple agent profiles can exist under each role.
- Peer suggestion confidence gets a +0.2 boost when the requesting role matches the stored role — a worker learns more from another worker.
- Role isolation: planner knowledge does not mix with worker knowledge unless a cross-role pattern emerges (guild meetings detect these).
- Guild meetings (cond guild meet) produce per-role knowledge digests showing what each role has learned.
- All agents share awareness of the edge events catalog (docs/guild/EDGE_EVENTS.md). This is the common vocabulary — every agent profile links to it via events_ref.
- Knowledge includes: capability name, error class, resolved input adjustments, success/failure counts, and confidence scores.
