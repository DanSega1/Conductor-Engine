---
name: http-capability
description: HTTP client capability for making outbound web requests. Supports GET, POST, PUT, DELETE with headers, JSON/query params, and timeout.
mode: subagent
engine_ref: engine/capabilities/http.py::HTTPCapability
events_ref: docs/guild/EDGE_EVENTS.md
risk_level: medium
---

- Supports GET, POST, PUT, DELETE methods.
- Accepts url, method, headers (dict), params (dict), json_body (dict), timeout_seconds.
- Returns status_code, headers, body, and elapsed time.
- No internal network restrictions — caller is responsible for access control.
