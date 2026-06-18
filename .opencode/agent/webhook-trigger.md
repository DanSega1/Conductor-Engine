---
name: webhook-trigger
description: Webhook-based trigger adapter. Receives decoded webhook payloads and maps them to TaskSubmissions.
mode: subagent
engine_ref: engine/runtime/scheduler.py::WebhookTriggerAdapter
events_ref: docs/guild/EDGE_EVENTS.md
---

- Receive a decoded webhook payload (dict with headers, body, method, source_ip).
- Map the payload to a TaskSubmission template (capability, input, metadata from webhook content).
- Preserve trigger provenance metadata in the submission metadata (trigger_name, source, received_at).
- Return the resulting TaskSubmission for supervisor dispatch.
