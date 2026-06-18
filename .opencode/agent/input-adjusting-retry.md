---
name: input-adjusting-retry
description: Retries with input adjustment — modifies the task input on each retry attempt (e.g., different parameters, relaxed constraints).
mode: subagent
engine_ref: engine/runtime/retry.py::InputAdjustingRetryStrategy
events_ref: docs/guild/EDGE_EVENTS.md
---

- On each retry, apply an adjustment function to the task input (e.g., reduce batch size, change parameters, add retry flag).
- Pass the adjusted input back in RetryDecision.adjusted_input so the supervisor updates task.input before retrying.
- Useful for capabilities where different inputs may succeed (API calls with backoff parameters, file operations with fallback paths).
- Also supports delay and escalation threshold like the base retry strategy.
