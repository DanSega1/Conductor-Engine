"""Subprocess-isolated capability execution.

``SubprocessCapabilityRunner`` executes a capability in a forked child
process so that misbehaving capabilities cannot:

- block the supervisor thread indefinitely (hard timeout via ``subprocess.run``)
- modify the parent process's in-memory state
- hold OS resources that the parent cannot reclaim

Architecture
------------
The runner serialises the capability input + context to JSON, invokes
``python -m engine.runtime._sandbox_worker`` in a child process, and
deserialises the JSON result on the parent side.

The sandbox worker module is a thin ``__main__`` block that:
1. reads the task payload from stdin as JSON
2. imports and instantiates the capability class by import path
3. calls ``capability.execute(payload, context)``
4. writes the result (or error) to stdout as JSON

Fallback
--------
When subprocess isolation is not desired (tests, no-fork environments) use
the standard ``_execute_with_timeout`` path in ``engine/supervisor/service.py``
directly. ``SubprocessCapabilityRunner`` is opt-in — the supervisor uses it
only when explicitly configured via ``use_subprocess=True`` on the runner.

Usage
-----
    runner = SubprocessCapabilityRunner(timeout_seconds=30.0)
    result = runner.run(
        import_path="engine.capabilities.echo:EchoCapability",
        payload={"message": "hello"},
        context=CapabilityContext(task_id="t1", task_name="echo", workdir="/tmp"),
    )
    # result is a CapabilityResult
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from engine.interfaces.capability import CapabilityContext, CapabilityResult


class SubprocessCapabilityError(RuntimeError):
    """Raised when a sandboxed capability execution fails."""


class SubprocessCapabilityRunner:
    """Execute a capability in an isolated subprocess.

    Parameters
    ----------
    timeout_seconds:
        Hard wall-clock timeout for the child process.  When the child
        exceeds this, it is forcibly killed and a ``SubprocessCapabilityError``
        is raised.  ``None`` means no timeout.
    python_executable:
        Path to the Python interpreter to use.  Defaults to ``sys.executable``
        (same interpreter as the parent).
    extra_env:
        Additional environment variables merged into the child's environment.
        Useful for injecting secrets or config without touching the parent env.
    capture_stderr:
        When True, child stderr is captured and included in errors.
        When False (default), child stderr is discarded (avoids leaking
        internal details into structured error messages).
    """

    def __init__(
        self,
        *,
        timeout_seconds: float | None = 30.0,
        python_executable: str | None = None,
        extra_env: dict[str, str] | None = None,
        capture_stderr: bool = False,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable or sys.executable
        self.extra_env = dict(extra_env or {})
        self.capture_stderr = capture_stderr

    def run(
        self,
        *,
        import_path: str,
        payload: Any,
        context: CapabilityContext,
    ) -> CapabilityResult:
        """Execute the capability in a subprocess and return its result.

        Parameters
        ----------
        import_path:
            Module + class path of the capability, e.g.
            ``"engine.capabilities.echo:EchoCapability"``.
        payload:
            Validated capability input (dict or Pydantic model).
        context:
            Runtime execution context (task_id, task_name, workdir).

        Returns
        -------
        CapabilityResult
            The capability's output on success.

        Raises
        ------
        SubprocessCapabilityError
            On timeout, non-zero exit code, or JSON decode failure.
        """
        payload_data = payload if isinstance(payload, dict) else payload.model_dump(mode="json")
        stdin_data = json.dumps(
            {
                "import_path": import_path,
                "payload": payload_data,
                "context": context.model_dump(),
            }
        )

        import os

        child_env = {**os.environ, **self.extra_env}

        try:
            proc = subprocess.run(
                [self.python_executable, "-m", "engine.runtime._sandbox_worker"],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise SubprocessCapabilityError(
                f"Capability '{import_path}' exceeded {self.timeout_seconds}s sandbox timeout"
            ) from exc

        stderr_detail = (f"\nstderr: {proc.stderr.strip()}" if self.capture_stderr and proc.stderr.strip() else "")

        if proc.returncode != 0:
            try:
                error_payload = json.loads(proc.stdout)
                error_msg = error_payload.get("error", f"exit code {proc.returncode}")
            except (json.JSONDecodeError, AttributeError):
                error_msg = f"exit code {proc.returncode}"
            raise SubprocessCapabilityError(
                f"Sandboxed capability '{import_path}' failed: {error_msg}{stderr_detail}"
            )

        try:
            result_data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SubprocessCapabilityError(
                f"Sandboxed capability '{import_path}' returned invalid JSON{stderr_detail}"
            ) from exc

        if "error" in result_data:
            raise SubprocessCapabilityError(
                f"Sandboxed capability '{import_path}' raised: {result_data['error']}{stderr_detail}"
            )

        return CapabilityResult(
            output=result_data.get("output"),
            metadata=result_data.get("metadata", {}),
        )
