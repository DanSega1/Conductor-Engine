---
name: mcp-capability
description: MCP (Model Context Protocol) capability wrapper for addon-provided MCP executors. Concrete transport lives in conductor-mcp, not base engine.
mode: subagent
engine_ref: engine/capabilities/mcp.py::MCPCapability
events_ref: docs/guild/EDGE_EVENTS.md
risk_level: medium
---

- Wraps an MCP executor as a Conductor Engine capability.
- Connection and session management is handled by the conductor-mcp addon package.
- Core engine provides the Capability seam. MCP transport is addon-owned.
