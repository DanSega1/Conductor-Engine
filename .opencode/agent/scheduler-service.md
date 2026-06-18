---
name: scheduler-service
description: Scheduler lifecycle manager — polls adapters, submits dispatches, manages backoff and graceful shutdown.
mode: subagent
engine_ref: engine/runtime/scheduler.py::TriggerSchedulerService
events_ref: docs/guild/EDGE_EVENTS.md
---

- Hold a registry of TriggerAdapters (cron and webhook).
- On each cycle: poll every adapter, collect dispatches, submit each through supervisor.submit().
- If no dispatches in a cycle, increase idle backoff exponentially with jitter.
- Respect max-cycle config bounds. Shut down on stop-signal.
- Log each adapter poll result (dispatches count, adapters, cycle duration).
