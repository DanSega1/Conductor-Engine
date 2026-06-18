---
name: exponential-backoff-retry
description: Retries with exponential delay between attempts (2^n seconds). Preferred for transient failures like network timeouts.
mode: subagent
engine_ref: engine/runtime/retry.py::ExponentialBackoffRetryStrategy
events_ref: docs/guild/EDGE_EVENTS.md
---

- Calculate delay as base_delay * (2 ^ attempt). Default base_delay = 1 second.
- Capped at max_delay (default 60 seconds).
- If attempt <= max_retries, return should_retry=true with delay_seconds set.
- Honor escalation_threshold and escalate_on_exhaustion settings.
- No input adjustment.
