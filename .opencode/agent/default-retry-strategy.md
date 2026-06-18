---
name: default-retry-strategy
description: Default retry strategy — retries up to max_retries with escalation threshold support.
mode: subagent
engine_ref: engine/runtime/retry.py::DefaultRetryStrategy
events_ref: docs/guild/EDGE_EVENTS.md
---

- Decide whether to retry based on TaskRecord.max_retries and current attempt count.
- If attempt <= max_retries, return should_retry=true.
- If attempt > max_retries and escalate_on_exhaustion is enabled (and escalation threshold reached), set escalate=true.
- Otherwise return should_retry=false, escalate=false (task goes to FAILED).
- No delay, no input adjustment — simple attempt cap.
