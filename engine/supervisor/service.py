"""Minimal supervisor: Task -> Capability -> Result."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from queue import Queue
import threading
import time
from typing import Any

from engine.guardrails.validation import validate_task_submission
from engine.interfaces.capability import CapabilityContext
from engine.interfaces.escalation import EscalationPolicy
from engine.interfaces.event import EventBus, EventType, TaskEvent
from engine.interfaces.policy import PolicyContext, PolicyDecision, PolicyDecisionType, PolicyEngine
from engine.interfaces.retry import FailureContext, RetryStrategy
from engine.interfaces.task import AuditEntry, TaskRecord, TaskResult, TaskStatus, TaskSubmission
from engine.registry.capabilities import CapabilityRegistry
from engine.runtime.bus import NullEventBus
from engine.runtime.policy import NullPolicyEngine
from engine.runtime.queue import InMemoryTaskQueue
from engine.runtime.retry import DefaultRetryStrategy
from engine.runtime.store import TaskStore


def _now() -> datetime:
    return datetime.now(tz=UTC)


EXECUTABLE_STATUSES = {TaskStatus.PENDING, TaskStatus.APPROVED}


def _execute_with_timeout(callable_obj: Any, *, timeout_seconds: float | None) -> Any:
    if timeout_seconds is None:
        return callable_obj()

    result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, callable_obj()))
        except BaseException as exc:  # pragma: no cover - passthrough path
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(
            f"Capability execution exceeded {timeout_seconds:.2f}s soft timeout; work may continue in the background"
        )

    success, value = result_queue.get()
    if success:
        return value
    raise value


class TaskSupervisor:
    """Single-process task supervisor for the minimal engine runtime."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        store: TaskStore,
        queue: InMemoryTaskQueue | None = None,
        workdir: str | Path | None = None,
        event_bus: EventBus | None = None,
        policy_engine: PolicyEngine | None = None,
        retry_strategy: RetryStrategy | None = None,
        escalation_policy: EscalationPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.queue = queue or InMemoryTaskQueue()
        self.workdir = str(Path(workdir or Path.cwd()).resolve())
        self._bus: EventBus = event_bus if event_bus is not None else NullEventBus()
        self._policy: PolicyEngine = (
            policy_engine if policy_engine is not None else NullPolicyEngine()
        )
        self._retry_strategy: RetryStrategy = (
            retry_strategy if retry_strategy is not None else DefaultRetryStrategy()
        )
        self._escalation_policy: EscalationPolicy | None = escalation_policy
        self._execution_lock = threading.Lock()
        self._last_capability_start: dict[str, float] = {}

    def _append_audit(
        self,
        task: TaskRecord,
        *,
        actor: str,
        action: str,
        from_status: TaskStatus | None = None,
        to_status: TaskStatus | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        task.audit_trail.append(
            AuditEntry(
                timestamp=timestamp or _now(),
                actor=actor,
                action=action,
                from_status=from_status,
                to_status=to_status,
                metadata=dict(metadata or {}),
            )
        )

    def _save_task(self, task: TaskRecord, *, timestamp: datetime | None = None) -> TaskRecord:
        task.updated_at = timestamp or _now()
        self.store.save(task)
        return task

    def _emit_event(
        self,
        *,
        event_type: EventType,
        task: TaskRecord,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._bus.emit(
                TaskEvent(
                    event_type=event_type,
                    task_id=task.task_id,
                    task_name=task.name,
                    capability=task.capability,
                    status=task.status,
                    attempt=task.attempt,
                    workflow_id=task.workflow_id,
                    error=error,
                    metadata=dict(metadata or {}),
                )
            )
        except Exception:
            return

    def _transition_status(
        self,
        task: TaskRecord,
        *,
        to_status: TaskStatus,
        actor: str,
        action: str,
        event_type: EventType,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
        timestamp: datetime | None = None,
    ) -> TaskRecord:
        transition_time = timestamp or _now()
        previous_status = task.status
        task.status = to_status
        self._append_audit(
            task,
            actor=actor,
            action=action,
            from_status=previous_status,
            to_status=to_status,
            metadata=metadata,
            timestamp=transition_time,
        )
        self._save_task(task, timestamp=transition_time)
        self._emit_event(
            event_type=event_type,
            task=task,
            error=error,
            metadata=metadata,
        )
        return task

    def _build_submission(self, task: TaskRecord) -> TaskSubmission:
        return TaskSubmission(
            name=task.name,
            capability=task.capability,
            input=task.input,
            metadata=task.metadata,
            max_retries=task.max_retries,
            workflow_id=task.workflow_id,
        )

    def _wait_for_execution_window(self, capability_name: str) -> None:
        controls = self.registry.execution_controls(capability_name)
        min_interval_seconds = controls.min_interval_seconds
        if min_interval_seconds is None:
            return

        with self._execution_lock:
            now = time.monotonic()
            previous_start = self._last_capability_start.get(capability_name)
            if previous_start is not None:
                sleep_for = min_interval_seconds - (now - previous_start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                    now = time.monotonic()
            self._last_capability_start[capability_name] = now

    def _create_task_record(self, submission: TaskSubmission, *, enqueue: bool) -> TaskRecord:
        validate_task_submission(submission, self.registry)
        task = TaskRecord(
            name=submission.name,
            capability=submission.capability,
            input=submission.input,
            metadata=submission.metadata,
            max_retries=submission.max_retries,
            workflow_id=submission.workflow_id,
        )
        self._append_audit(
            task,
            actor="supervisor",
            action="submitted",
            to_status=TaskStatus.PENDING,
            metadata={"max_retries": task.max_retries},
            timestamp=task.created_at,
        )
        self.store.save(task)
        if enqueue:
            self.queue.enqueue(task.task_id)
        return task

    def _apply_policy(self, task: TaskRecord, decision: PolicyDecision) -> TaskRecord:
        policy_metadata = dict(decision.metadata)
        if decision.reason is not None:
            policy_metadata.setdefault("reason", decision.reason)

        if decision.decision == PolicyDecisionType.DENY:
            denied_at = _now()
            task.result = TaskResult(
                success=False,
                error=decision.reason or "Task denied by policy",
                metadata=policy_metadata,
                completed_at=denied_at,
            )
            return self._transition_status(
                task,
                to_status=TaskStatus.POLICY_DENIED,
                actor="policy",
                action="denied",
                event_type=EventType.TASK_POLICY_DENIED,
                metadata=policy_metadata,
                error=task.result.error,
                timestamp=denied_at,
            )

        if decision.decision == PolicyDecisionType.REQUIRE_APPROVAL:
            return self._transition_status(
                task,
                to_status=TaskStatus.AWAITING_APPROVAL,
                actor="policy",
                action="awaiting_approval",
                event_type=EventType.TASK_AWAITING_APPROVAL,
                metadata=policy_metadata,
            )

        self._append_audit(
            task,
            actor="policy",
            action="allowed",
            from_status=TaskStatus.PENDING,
            to_status=TaskStatus.PENDING,
            metadata=policy_metadata,
        )
        self._save_task(task)

        return task

    def _do_escalate(
        self,
        task: TaskRecord,
        failure_history: list[FailureContext],
        started_at: datetime,
        exc: BaseException,
        *,
        reason: str | None = None,
    ) -> None:
        escalated_at = _now()
        escalation_record = (
            self._escalation_policy.build_record(task, failure_history)
            if self._escalation_policy is not None
            else None
        )
        result_metadata: dict[str, Any] = {}
        if escalation_record is not None:
            result_metadata["escalation_record"] = escalation_record.model_dump()
        elif reason is not None:
            result_metadata["escalation_reason"] = reason
        task.result = TaskResult(
            success=False,
            error=str(exc),
            metadata=result_metadata,
            started_at=started_at,
            completed_at=escalated_at,
        )
        self._transition_status(
            task,
            to_status=TaskStatus.ESCALATED,
            actor="supervisor",
            action="escalated",
            event_type=EventType.TASK_ESCALATED,
            metadata={"attempt": task.attempt, "total_failures": len(failure_history)},
            error=task.result.error,
            timestamp=escalated_at,
        )

    def get_task(self, task_id: str) -> TaskRecord:
        task = self.store.get(task_id)
        if task is None:
            raise ValueError(f"Task '{task_id}' was not found")
        return task

    def submit(self, submission: TaskSubmission) -> TaskRecord:
        return self._create_task_record(submission, enqueue=True)

    def run_submission(self, submission: TaskSubmission) -> TaskRecord:
        task = self._create_task_record(submission, enqueue=False)
        return self.run_task(task.task_id)

    def run_next(self) -> TaskRecord:
        task_id = self.queue.dequeue()
        if task_id is None:
            raise ValueError("No queued tasks are available")
        return self.run_task(task_id)

    def run_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)

        if task.status not in EXECUTABLE_STATUSES:
            return task

        submission = self._build_submission(task)
        capability = validate_task_submission(submission, self.registry)

        if task.status == TaskStatus.PENDING:
            decision = self._policy.evaluate(
                task.model_copy(deep=True),
                PolicyContext(capability=capability.descriptor, workdir=self.workdir),
            )
            task = self._apply_policy(task, decision)
            if task.status != TaskStatus.PENDING:
                return task

        controls = self.registry.execution_controls(task.capability)
        self._wait_for_execution_window(task.capability)

        started_at = _now()
        task.attempt += 1
        self._transition_status(
            task,
            to_status=TaskStatus.RUNNING,
            actor="supervisor",
            action="started",
            event_type=EventType.TASK_STARTED,
            metadata={"attempt": task.attempt, "max_retries": task.max_retries},
            timestamp=started_at,
        )

        last_exc: Exception | None = None
        failure_history: list[FailureContext] = []
        while True:
            try:
                payload = capability.validate_input(task.input)
                execution_context = CapabilityContext(
                    task_id=task.task_id,
                    task_name=task.name,
                    workdir=self.workdir,
                )
                result = _execute_with_timeout(
                    lambda validated_payload=payload, context=execution_context: capability.execute(
                        validated_payload,
                        context,
                    ),
                    timeout_seconds=controls.timeout_seconds,
                )
                task.result = TaskResult(
                    success=True,
                    output=result.output,
                    metadata=result.metadata,
                    started_at=started_at,
                    completed_at=_now(),
                )
                last_exc = None
                self._transition_status(
                    task,
                    to_status=TaskStatus.COMPLETED,
                    actor="supervisor",
                    action="completed",
                    event_type=EventType.TASK_COMPLETED,
                    metadata={"attempt": task.attempt},
                    timestamp=task.result.completed_at,
                )
                break
            except Exception as exc:
                last_exc = exc

                # Build failure context
                input_fingerprint = hashlib.sha256(
                    json.dumps(task.input, sort_keys=True).encode()
                ).hexdigest()[:16]

                failure = FailureContext(
                    task_id=task.task_id,
                    capability=task.capability,
                    attempt=task.attempt,
                    max_retries=task.max_retries,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    input_fingerprint=input_fingerprint,
                )
                failure_history.append(failure)

                # Persist failure context in audit trail
                failure_metadata = failure.model_dump()
                self._append_audit(
                    task,
                    actor="supervisor",
                    action="failure_recorded",
                    metadata=failure_metadata,
                )
                self._save_task(task)

                # Ask retry strategy for decision
                decision = self._retry_strategy.decide(task, failure)

                if not decision.should_retry:
                    if decision.escalate or (
                        self._escalation_policy
                        and self._escalation_policy.should_escalate(task, failure_history)
                    ):
                        self._do_escalate(
                            task,
                            failure_history,
                            started_at,
                            exc,
                            reason=decision.reason if decision.escalate else None,
                        )
                        last_exc = None
                    break

                # Would retry — increment attempt, then check escalation policy
                task.attempt += 1
                if decision.adjusted_input is not None:
                    task.input = decision.adjusted_input

                if self._escalation_policy and self._escalation_policy.should_escalate(
                    task, failure_history
                ):
                    self._do_escalate(task, failure_history, started_at, exc)
                    last_exc = None
                    break

                retry_metadata = {
                    "attempt": task.attempt,
                    "previous_attempt": task.attempt - 1,
                    "max_retries": task.max_retries,
                    "error": str(exc),
                    "retry_reason": decision.reason,
                }
                if decision.adjusted_input is not None:
                    retry_metadata["input_adjusted"] = True

                self._append_audit(
                    task,
                    actor="supervisor",
                    action="retry",
                    from_status=TaskStatus.RUNNING,
                    to_status=TaskStatus.RUNNING,
                    metadata=retry_metadata,
                )
                self._save_task(task)
                self._emit_event(
                    event_type=EventType.TASK_RETRY,
                    task=task,
                    error=str(exc),
                    metadata=retry_metadata,
                )

                if decision.delay_seconds is not None and decision.delay_seconds > 0:
                    time.sleep(decision.delay_seconds)

        if last_exc is not None:
            failed_at = _now()
            task.result = TaskResult(
                success=False,
                error=str(last_exc),
                started_at=started_at,
                completed_at=failed_at,
            )
            self._transition_status(
                task,
                to_status=TaskStatus.FAILED,
                actor="supervisor",
                action="failed",
                event_type=EventType.TASK_FAILED,
                metadata={"attempt": task.attempt},
                error=task.result.error,
                timestamp=failed_at,
            )

        return task

    def approve_task(
        self,
        task_id: str,
        *,
        actor: str = "user",
        metadata: dict[str, Any] | None = None,
        run: bool = True,
    ) -> TaskRecord:
        task = self.get_task(task_id)
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise ValueError(f"Task '{task_id}' is not awaiting approval")

        approved = self._transition_status(
            task,
            to_status=TaskStatus.APPROVED,
            actor=actor,
            action="approved",
            event_type=EventType.TASK_APPROVED,
            metadata=metadata,
        )
        if not run:
            self.queue.enqueue(task_id)
            return approved
        return self.run_task(task_id)

    def cancel_task(
        self,
        task_id: str,
        *,
        actor: str = "user",
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord:
        task = self.get_task(task_id)
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise ValueError(f"Task '{task_id}' cannot be cancelled from status '{task.status}'")

        cancellation_metadata = dict(metadata or {})
        if reason is not None:
            cancellation_metadata.setdefault("reason", reason)
        cancelled_at = _now()
        task.result = TaskResult(
            success=False,
            error=reason or "Task cancelled",
            metadata=cancellation_metadata,
            completed_at=cancelled_at,
        )
        return self._transition_status(
            task,
            to_status=TaskStatus.CANCELLED,
            actor=actor,
            action="cancelled",
            event_type=EventType.TASK_CANCELLED,
            metadata=cancellation_metadata,
            error=task.result.error,
            timestamp=cancelled_at,
        )

    def list_tasks(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: TaskStatus | str | None = None,
    ) -> list[TaskRecord]:
        status_value = status.value if isinstance(status, TaskStatus) else status
        return self.store.list(limit=limit, offset=offset, status=status_value)

    def health_check(self) -> list[str]:
        issues: list[str] = []
        workdir = Path(self.workdir)
        if not workdir.exists():
            issues.append(f"supervisor: workdir '{workdir}' does not exist")
        elif not workdir.is_dir():
            issues.append(f"supervisor: workdir '{workdir}' is not a directory")
        return issues
