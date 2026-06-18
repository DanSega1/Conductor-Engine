---
name: subprocess-runner
description: Sandboxed subprocess capability execution. Runs capabilities in isolated child processes with hard wall-clock timeout, no shared state, and clean resource reclamation.
mode: subagent
engine_ref: engine/runtime/sandbox.py::SubprocessCapabilityRunner
events_ref: docs/guild/EDGE_EVENTS.md
---

- Execute capabilities in isolated child processes via multiprocessing or subprocess.
- Enforce a hard wall-clock timeout on the child process. If exceeded, kill the process and mark task FAILED.
- No shared state between parent and child — capability receives input via pickle/serialization and returns result via the same.
- Clean resource reclamation on timeout or crash (close FDs, reap zombie processes).
- Opt-in only — the default in-process execution path is unchanged. Use for high-risk capabilities or hard timeouts.
