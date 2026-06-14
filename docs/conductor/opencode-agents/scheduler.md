# Scheduler Agent

**Config:** `.opencode/agents/scheduler/scheduler.json`
**Engine ref:** `engine/runtime/scheduler.py`
**Priority:** 11
**Role:** Cron and webhook trigger adapters with polling scheduler lifecycle.

## Purpose

The scheduler manages time-based (cron) and event-based (webhook) triggers. A `TriggerSchedulerService` polls registered adapters on a configurable interval, collects pending dispatches, and submits each as a `TaskSubmission` through the supervisor path. A `TriggerSchedulerLoopRunner` manages the lifecycle with exponential idle backoff, jitter, max-cycle bounds, and graceful stop-signal shutdown.

## Invariants

- All dispatches go through the supervisor path (`supervisor.submit()` or `supervisor.run_submission()`).
- Adapters are deterministic — no external dependencies for cron matching.
- Webhook ingress is exposed via `POST /v1/triggers/{name}` on the control-plane API.
- Idle backoff prevents busy-polling when no triggers are scheduled.

## Subagents

| Subagent | Engine ref | Purpose |
|---|---|---|
| cron-trigger | `engine/runtime/scheduler.py::CronTriggerAdapter` | Matches 5-field cron expressions. Returns TaskSubmission template on match. |
| webhook-trigger | `engine/runtime/scheduler.py::WebhookTriggerAdapter` | Maps decoded webhook payload to TaskSubmission. Preserves trigger provenance. |
| scheduler-service | `engine/runtime/scheduler.py::TriggerSchedulerService` | Polls adapters, collects dispatches, submits through supervisor. |
| webhook-ingress | `engine/runtime/scheduler.py::WebhookIngressService` | Decodes HTTP requests, routes to named adapters. |

## Execution contract

```
TriggerSchedulerService:
  poll_cycle():
    for each adapter:
      dispatches = adapter.poll()
      for each dispatch:
        supervisor.submit(dispatch.submission)

WebhookIngressService:
  receive(trigger_name, headers, body):
    adapter = adapters[trigger_name]
    submission = adapter.map_payload(headers, body)
    supervisor.run_submission(submission)
```

## Lifecycle

```
TriggerSchedulerLoopRunner.start()
  → loop:
      dispatches = scheduler.poll_cycle()
      if dispatches == 0:
        backoff *= 2 (with jitter, capped)
      else:
        backoff = initial_interval
      sleep(backoff)
  → on stop_signal(): graceful shutdown
```

## When to use

- cron-trigger: periodic task execution (backup, report generation, health checks)
- webhook-trigger: event-driven execution (GitHub webhook → capability execution)
- scheduler-service: when multiple triggers need lifecycle management
- webhook-ingress: when the HTTP API needs to receive external webhook calls
