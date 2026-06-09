"""Sandbox worker — executed in a subprocess by SubprocessCapabilityRunner.

This module is the ``__main__`` entry point for sandboxed capability execution.
It is NOT intended to be imported directly.  The runner spawns it via::

    python -m engine.runtime._sandbox_worker

Protocol
--------
- Reads a single JSON object from stdin:
    {
      "import_path": "package.module:ClassName",
      "payload": {...},
      "context": {"task_id": ..., "task_name": ..., "workdir": ...}
    }

- Writes a single JSON object to stdout:
    Success: {"output": <any>, "metadata": {...}}
    Failure: {"error": "<message>"}

- Exits 0 on success, 1 on any error.

Security notes
--------------
- The worker runs in a fresh process with its own memory space.
- The parent process provides ``import_path`` — callers must ensure only
  trusted capability classes are referenced (see registry validation).
- No environment secrets are injected unless the runner explicitly passes them.
"""

from __future__ import annotations

import json
import sys
import traceback
from importlib import import_module


def _main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": f"stdin parse error: {exc}"}))
        sys.stdout.flush()
        sys.exit(1)

    import_path: str = data.get("import_path", "")
    payload: dict = data.get("payload", {})
    context_data: dict = data.get("context", {})

    try:
        module_name, _, class_name = import_path.partition(":")
        if not module_name or not class_name:
            raise ValueError(f"Invalid import_path: {import_path!r}")
        module = import_module(module_name)
        capability_class = getattr(module, class_name)
        capability = capability_class()
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": f"capability load error: {exc}"}))
        sys.stdout.flush()
        sys.exit(1)

    try:
        from engine.interfaces.capability import CapabilityContext

        context = CapabilityContext.model_validate(context_data)
        validated = capability.validate_input(payload)
        result = capability.execute(validated, context)
        output_data = result.output
        if hasattr(output_data, "model_dump"):
            output_data = output_data.model_dump(mode="json")
        sys.stdout.write(
            json.dumps({"output": output_data, "metadata": dict(result.metadata)})
        )
        sys.stdout.flush()
        sys.exit(0)
    except Exception as exc:
        tb = traceback.format_exc()
        sys.stdout.write(
            json.dumps({"error": f"{type(exc).__name__}: {exc}", "traceback": tb})
        )
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    _main()
