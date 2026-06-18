---
name: cron-trigger
description: Cron expression–based trigger adapter. Polls on scheduler interval and fires when cron expression matches current time.
mode: subagent
engine_ref: engine/runtime/scheduler.py::CronTriggerAdapter
events_ref: docs/guild/EDGE_EVENTS.md
---

- Configured with a cron expression (standard 5-field format), a TaskSubmission template, and a name.
- On each poll, check if the cron expression matches the current time (within tolerance).
- If matched, return a dispatch containing the TaskSubmission template.
- Avoid double-firing within the same minute window.
- Deterministic — no external dependencies.
