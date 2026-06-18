---
name: filesystem-capability
description: Filesystem read/write operations. Supports write_text, read_text, list_dir, delete, and exists actions. Path-traversal protected.
mode: subagent
engine_ref: engine/capabilities/filesystem.py::FilesystemCapability
events_ref: docs/guild/EDGE_EVENTS.md
risk_level: high
---

- Actions: write_text, read_text, list_dir, delete, exists.
- All paths are resolved relative to the capability workdir. Path traversal (../) is rejected by guardrails.
- Always validate the action parameter before operating on the filesystem.
- Return output with the action result and normalized path.
