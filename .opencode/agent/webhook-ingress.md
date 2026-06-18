---
name: webhook-ingress
description: Webhook ingress boundary — decodes incoming webhook HTTP requests and routes to named adapters.
mode: subagent
engine_ref: engine/runtime/scheduler.py::WebhookIngressService
events_ref: docs/guild/EDGE_EVENTS.md
---

- Receive an HTTP request with trigger name, headers, body, query params.
- Decode the payload (JSON body, form-encoded, or raw text depending on Content-Type).
- Route to the named WebhookTriggerAdapter.
- Return 200 on successful dispatch, 404 if trigger name is unknown, 400 on malformed payload.
- Submit the resulting TaskSubmission to the supervisor.
