"""Stress tests and benchmarks for the full Conductor Engine stack.

Integration/load tests using real supervisors, real capabilities, and the real
orchestrator.  No mocks — all assertions against actual execution results.
"""

from __future__ import annotations

import string
import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from engine.interfaces.capability import (
    Capability,
    CapabilityContext,
    CapabilityDescriptor,
    CapabilityResult,
)
from engine.interfaces.task import TaskStatus, TaskSubmission
from engine.interfaces.workflow import (
    PlanStep,
    WorkerContext,
    WorkerResponse,
    WorkflowGoal,
    WorkflowStatus,
)
from engine.loader import load_capabilities
from engine.runtime.store import MemoryTaskStore
from engine.supervisor.service import TaskSupervisor
from engine.workflow.agents import LinearPlanner, PassthroughValidator, PassthroughWorker
from engine.workflow.orchestrator import WorkflowOrchestrator

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_supervisor(tmp_path: Path) -> TaskSupervisor:
    registry = load_capabilities(base_path=tmp_path)
    store = MemoryTaskStore()
    return TaskSupervisor(registry=registry, store=store, workdir=tmp_path)


def _make_orchestrator(steps: list[PlanStep], tmp_path: Path) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=LinearPlanner(steps=steps),
        worker=PassthroughWorker(),
        validator=PassthroughValidator(),
        supervisor=_make_supervisor(tmp_path),
    )


# ---------------------------------------------------------------------------
# BombCapability — always raises, used for retry exhaustion tests
# ---------------------------------------------------------------------------


class _BombInput(BaseModel):
    pass


class BombCapability(Capability):
    input_model = _BombInput

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(name="bomb", description="always fails")

    def execute(
        self,
        payload: BaseModel | dict,
        context: CapabilityContext,
    ) -> CapabilityResult:
        raise RuntimeError("intentional failure")


def _make_supervisor_with_bomb(tmp_path: Path) -> TaskSupervisor:
    """Supervisor with all built-ins plus the BombCapability registered."""
    registry = load_capabilities(base_path=tmp_path)
    registry._capabilities["bomb"] = BombCapability()
    store = MemoryTaskStore()
    return TaskSupervisor(registry=registry, store=store, workdir=tmp_path)


# ---------------------------------------------------------------------------
# GROUP 1: Volume / scale
# ---------------------------------------------------------------------------


def test_large_echo_workflow_100_steps(tmp_path: Path) -> None:
    """100 echo steps — all complete, all outputs match their input messages."""
    steps = [
        PlanStep(name=f"step-{i}", capability="echo", input_hint={"message": f"msg-{i}"})
        for i in range(100)
    ]
    orchestrator = _make_orchestrator(steps, tmp_path)
    result = orchestrator.run(WorkflowGoal(goal="100-step echo"))

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.records) == 100
    for i, record in enumerate(result.records):
        assert record.status == TaskStatus.COMPLETED
        assert record.result is not None
        assert record.result.output["message"] == f"msg-{i}"


def test_bulk_independent_tasks_via_supervisor(tmp_path: Path) -> None:
    """500 echo tasks submitted and run directly through the supervisor (no orchestrator)."""
    supervisor = _make_supervisor(tmp_path)
    records = []
    for i in range(500):
        submission = TaskSubmission(
            name=f"bulk-{i}",
            capability="echo",
            input={"message": f"bulk-msg-{i}"},
        )
        record = supervisor.run_submission(submission)
        records.append(record)

    assert len(records) == 500
    assert all(r.status == TaskStatus.COMPLETED for r in records)

    stored = supervisor.list_tasks()
    assert len(stored) == 500


def test_filesystem_workflow_write_then_read_50_files(tmp_path: Path) -> None:
    """50 write steps then 50 read steps. Assert all reads return expected content."""
    write_steps = [
        PlanStep(
            name=f"write-{i}",
            capability="filesystem",
            input_hint={
                "action": "write_text",
                "path": f"file_{i}.txt",
                "content": f"content-{i}",
            },
        )
        for i in range(50)
    ]
    read_steps = [
        PlanStep(
            name=f"read-{i}",
            capability="filesystem",
            input_hint={"action": "read_text", "path": f"file_{i}.txt"},
        )
        for i in range(50)
    ]

    orchestrator = _make_orchestrator(write_steps + read_steps, tmp_path)
    result = orchestrator.run(WorkflowGoal(goal="write-read 50 files"))

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.records) == 100

    for i, record in enumerate(result.records[50:], start=0):
        assert record.status == TaskStatus.COMPLETED
        assert record.result is not None
        assert record.result.output["content"] == f"content-{i}"


# ---------------------------------------------------------------------------
# GROUP 2: Retry stress
# ---------------------------------------------------------------------------


def test_retry_exhaustion_under_load(tmp_path: Path) -> None:
    """20 tasks against BombCapability with max_retries=3. All must end FAILED."""
    supervisor = _make_supervisor_with_bomb(tmp_path)
    records = []
    for i in range(20):
        submission = TaskSubmission(
            name=f"retry-task-{i}",
            capability="bomb",
            input={},
            max_retries=3,
        )
        task = supervisor.submit(submission)
        record = supervisor.run_task(task.task_id)
        records.append(record)

    assert len(records) == 20
    for record in records:
        assert record.status == TaskStatus.FAILED
        assert record.attempt >= 1


def test_workflow_retries_all_steps(tmp_path: Path) -> None:
    """10-step workflow targeting bomb. Fail-fast after step 1; exactly 1 record, FAILED."""
    supervisor = _make_supervisor_with_bomb(tmp_path)
    steps = [
        PlanStep(name=f"bomb-step-{i}", capability="bomb", input_hint={})
        for i in range(10)
    ]
    orchestrator = WorkflowOrchestrator(
        planner=LinearPlanner(steps=steps),
        worker=PassthroughWorker(),
        validator=PassthroughValidator(),
        supervisor=supervisor,
    )
    result = orchestrator.run(WorkflowGoal(goal="all-bomb workflow"))

    assert result.status == WorkflowStatus.FAILED
    assert len(result.records) == 1
    assert result.records[0].status == TaskStatus.FAILED
    assert result.records[0].attempt >= 1


# ---------------------------------------------------------------------------
# GROUP 3: Data integrity
# ---------------------------------------------------------------------------


class ChainWorker:
    """Worker that builds a cumulative chain by prepending the previous step's message."""

    def work(self, step_name: str, context: WorkerContext) -> WorkerResponse:
        base_message = context.step.input_hint.get("message", "")
        if context.prior_results:
            prev_output = context.prior_results[-1].result
            if prev_output and prev_output.output and "message" in prev_output.output:
                base_message = prev_output.output["message"] + "|" + base_message
        return WorkerResponse(
            submission=TaskSubmission(
                name=step_name,
                capability=context.step.capability,
                input={"message": base_message},
            )
        )


def test_workflow_prior_results_chain_50_steps(tmp_path: Path) -> None:
    """50-step echo chain. Final record's output must contain content from earlier steps."""
    steps = [
        PlanStep(name=f"chain-{i}", capability="echo", input_hint={"message": f"s{i}"})
        for i in range(50)
    ]
    supervisor = _make_supervisor(tmp_path)
    orchestrator = WorkflowOrchestrator(
        planner=LinearPlanner(steps=steps),
        worker=ChainWorker(),
        validator=PassthroughValidator(),
        supervisor=supervisor,
    )
    result = orchestrator.run(WorkflowGoal(goal="chain 50 steps"))

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.records) == 50

    final_message = result.records[-1].result.output["message"]
    # The chain grows — the final message must reference content from earlier steps
    assert "s0" in final_message
    assert "s49" in final_message


def test_memory_store_isolation(tmp_path: Path) -> None:
    """3 orchestrators with 3 separate stores. Each must have exactly 10 records, no bleed."""
    all_records = []
    stores = []

    for run_idx in range(3):
        store = MemoryTaskStore()
        stores.append(store)
        registry = load_capabilities(base_path=tmp_path)
        supervisor = TaskSupervisor(registry=registry, store=store, workdir=tmp_path)
        steps = [
            PlanStep(
                name=f"iso-{run_idx}-{i}",
                capability="echo",
                input_hint={"message": f"run{run_idx}-step{i}"},
            )
            for i in range(10)
        ]
        orchestrator = WorkflowOrchestrator(
            planner=LinearPlanner(steps=steps),
            worker=PassthroughWorker(),
            validator=PassthroughValidator(),
            supervisor=supervisor,
        )
        result = orchestrator.run(WorkflowGoal(goal=f"isolation-{run_idx}"))
        assert result.status == WorkflowStatus.COMPLETED
        all_records.append(store.list())

    for idx, records in enumerate(all_records):
        assert len(records) == 10, f"Store {idx} has {len(records)} records, expected 10"

    # Task IDs must be globally unique — no cross-contamination
    all_ids = [r.task_id for records in all_records for r in records]
    assert len(all_ids) == len(set(all_ids)), "Duplicate task IDs across stores — contamination!"

    # Records in store A must not appear in stores B or C
    for i in range(3):
        ids_in_i = {r.task_id for r in all_records[i]}
        for j in range(3):
            if i == j:
                continue
            ids_in_j = {r.task_id for r in all_records[j]}
            overlap = ids_in_i & ids_in_j
            assert not overlap, f"Store {i} and Store {j} share task IDs: {overlap}"


# ---------------------------------------------------------------------------
# GROUP 4: Benchmarks
# ---------------------------------------------------------------------------


def test_benchmark_echo_throughput(tmp_path: Path) -> None:
    """1000 echo tasks via supervisor. Must complete in under 5 seconds."""
    supervisor = _make_supervisor(tmp_path)
    start = time.perf_counter()

    for i in range(1000):
        submission = TaskSubmission(
            name=f"bench-{i}",
            capability="echo",
            input={"message": f"bench-msg-{i}"},
        )
        supervisor.run_submission(submission)

    elapsed = time.perf_counter() - start
    print(f"\n1000 echo tasks: {elapsed:.3f}s ({1000 / elapsed:.0f} tasks/sec)")
    assert elapsed < 5.0, f"Throughput too slow: {elapsed:.3f}s for 1000 tasks"


def test_benchmark_orchestrator_50_step_workflow(tmp_path: Path) -> None:
    """50-step echo workflow run 10 times. Average must be under 0.5 seconds per run."""
    steps = [
        PlanStep(name=f"bench-step-{i}", capability="echo", input_hint={"message": f"m{i}"})
        for i in range(50)
    ]

    total_start = time.perf_counter()
    for _ in range(10):
        orchestrator = _make_orchestrator(steps, tmp_path)
        result = orchestrator.run(WorkflowGoal(goal="benchmark 50-step workflow"))
        assert result.status == WorkflowStatus.COMPLETED

    total = time.perf_counter() - total_start
    avg = total / 10
    print(f"\n50-step workflow x10: {total:.3f}s avg={avg:.3f}s/run")
    assert avg < 0.5, f"Average run too slow: {avg:.3f}s (must be < 0.5s)"


# ---------------------------------------------------------------------------
# GROUP 5: Edge cases
# ---------------------------------------------------------------------------


def test_empty_workflow_completes_immediately(tmp_path: Path) -> None:
    """Zero-step workflow. Must complete immediately with empty records and passed verdict."""
    orchestrator = _make_orchestrator([], tmp_path)
    result = orchestrator.run(WorkflowGoal(goal="empty workflow"))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.records == []
    assert result.verdict is not None
    assert result.verdict.passed is True


def test_single_character_messages(tmp_path: Path) -> None:
    """26 echo steps with messages 'a' through 'z'. All must complete and output must match."""
    steps = [
        PlanStep(name=f"char-{c}", capability="echo", input_hint={"message": c})
        for c in string.ascii_lowercase
    ]
    orchestrator = _make_orchestrator(steps, tmp_path)
    result = orchestrator.run(WorkflowGoal(goal="alphabet echo"))

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.records) == 26
    for record, char in zip(result.records, string.ascii_lowercase):
        assert record.status == TaskStatus.COMPLETED
        assert record.result.output["message"] == char


def test_large_message_payload(tmp_path: Path) -> None:
    """Single echo step with a 100KB string. Output must match input exactly."""
    large_message = "x" * (100 * 1024)
    steps = [PlanStep(name="big-echo", capability="echo", input_hint={"message": large_message})]
    orchestrator = _make_orchestrator(steps, tmp_path)
    result = orchestrator.run(WorkflowGoal(goal="large payload"))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.records[0].result.output["message"] == large_message


def test_filesystem_write_large_file(tmp_path: Path) -> None:
    """Write a 1MB file then read it back. Byte count must match."""
    one_mb_content = "a" * (1024 * 1024)
    expected_bytes = len(one_mb_content.encode())

    write_step = PlanStep(
        name="write-1mb",
        capability="filesystem",
        input_hint={
            "action": "write_text",
            "path": "large_file.txt",
            "content": one_mb_content,
        },
    )
    read_step = PlanStep(
        name="read-1mb",
        capability="filesystem",
        input_hint={"action": "read_text", "path": "large_file.txt"},
    )

    orchestrator = _make_orchestrator([write_step, read_step], tmp_path)
    result = orchestrator.run(WorkflowGoal(goal="1mb file roundtrip"))

    assert result.status == WorkflowStatus.COMPLETED
    write_output = result.records[0].result.output
    assert write_output["bytes_written"] == expected_bytes

    read_output = result.records[1].result.output
    assert len(read_output["content"].encode()) == expected_bytes


def test_workflow_goal_id_preserved_across_100_runs(tmp_path: Path) -> None:
    """Same WorkflowGoal run 100 times. All results must carry the same workflow_id."""
    goal = WorkflowGoal(goal="id preservation check")
    steps = [PlanStep(name="id-echo", capability="echo", input_hint={"message": "hi"})]

    for _ in range(100):
        orchestrator = _make_orchestrator(steps, tmp_path)
        result = orchestrator.run(goal)
        assert result.workflow_id == goal.workflow_id
