---
name: jittered-backoff-retry
description: Retries with exponential backoff plus random jitter to avoid thundering herd.
mode: subagent
engine_ref: engine/runtime/retry.py::JitteredBackoffRetryStrategy
events_ref: docs/guild/EDGE_EVENTS.md
---

- Calculate delay as exponential backoff, then add random jitter within +-jitter_fraction range (default 0.25).
- Example: base delay 4s, jitter fraction 0.25 => delay between 3s and 5s.
- Capped at max_delay.
- Useful when multiple tasks may fail simultaneously and retry in lockstep.
