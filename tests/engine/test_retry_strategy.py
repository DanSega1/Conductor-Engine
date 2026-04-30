"""Tests for behavioral retry strategy."""


import pytest

from engine.interfaces.retry import FailureContext, RetryDecision
from engine.interfaces.task import TaskRecord
from engine.runtime.retry import DefaultRetryStrategy


class TestDefaultRetryStrategy:
    """Test suite for DefaultRetryStrategy."""

    def test_retry_when_attempts_remaining(self):
        """Should retry when attempt count has not exceeded max_retries."""
        strategy = DefaultRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is True
        assert decision.escalate is False
        assert "Retry 1 of 3" in decision.reason

    def test_no_retry_when_attempts_exhausted(self):
        """Should not retry when attempt count exceeds max_retries."""
        strategy = DefaultRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=4,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False
        assert "exhausted" in decision.reason.lower()

    def test_no_retry_with_zero_max_retries(self):
        """Should not retry when max_retries is 0 (default)."""
        strategy = DefaultRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=0,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=1,
            max_retries=0,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False

    def test_escalation_disabled_by_default(self):
        """Should not escalate by default when retries exhausted."""
        strategy = DefaultRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=4,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False

    def test_escalation_when_enabled(self):
        """Should escalate when enabled and retries exhausted."""
        strategy = DefaultRetryStrategy(enable_escalation=True)
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=4,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True

    def test_no_escalation_while_retries_available(self):
        """Should not escalate when retries are still available."""
        strategy = DefaultRetryStrategy(enable_escalation=True)
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=2,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=2,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is True
        assert decision.escalate is False

    def test_escalation_threshold_met(self):
        """Should escalate when enabled and attempt meets the threshold."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=5)
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=5,
            max_retries=4,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=5,
            max_retries=4,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True

    def test_escalation_threshold_not_met(self):
        """Should NOT escalate when retries exhausted but attempt is below threshold."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=10)
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=4,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False

    def test_escalation_threshold_none_escalates_on_any_exhaustion(self):
        """With threshold=None, any exhaustion triggers escalation when enabled."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=None)
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=0,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=1,
            max_retries=0,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True

    def test_escalation_threshold_ignored_when_escalation_disabled(self):
        """escalation_threshold has no effect when enable_escalation=False."""
        strategy = DefaultRetryStrategy(enable_escalation=False, escalation_threshold=1)
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=5,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=5,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False

    def test_no_input_adjustment(self):
        """Default strategy should not adjust inputs."""
        strategy = DefaultRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=3,
            input={"message": "test"},
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.adjusted_input is None

    def test_no_delay(self):
        """Default strategy should not add delays."""
        strategy = DefaultRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.delay_seconds is None

    # NOTE: requires McManus slice 2 implementation
    @pytest.mark.xfail(reason="requires McManus slice 2: escalation_threshold on DefaultRetryStrategy", strict=False)
    def test_escalation_threshold_none_escalates_on_exhaustion(self):
        """enable_escalation=True, threshold=None → escalate on any exhaustion."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=None)
        task = TaskRecord(name="test", capability="echo", attempt=4, max_retries=3)
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True

    # NOTE: requires McManus slice 2 implementation
    @pytest.mark.xfail(reason="requires McManus slice 2: escalation_threshold on DefaultRetryStrategy", strict=False)
    def test_escalation_threshold_set_escalates_at_or_above_threshold(self):
        """enable_escalation=True, threshold=3 → escalate when attempt >= threshold on exhaustion."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=3)
        task = TaskRecord(name="test", capability="echo", attempt=4, max_retries=3)
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True

    # NOTE: requires McManus slice 2 implementation
    @pytest.mark.xfail(reason="requires McManus slice 2: escalation_threshold on DefaultRetryStrategy", strict=False)
    def test_escalation_threshold_set_no_escalation_below_threshold(self):
        """enable_escalation=True, threshold=3 → FAILED (not escalate) when attempt < threshold."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=3)
        task = TaskRecord(name="test", capability="echo", attempt=2, max_retries=1)
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=2,
            max_retries=1,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False

    # NOTE: requires McManus slice 2 implementation
    @pytest.mark.xfail(reason="requires McManus slice 2: escalation_threshold on DefaultRetryStrategy", strict=False)
    def test_escalation_disabled_with_threshold_never_escalates(self):
        """enable_escalation=False, threshold=3 → never escalate regardless of attempt."""
        strategy = DefaultRetryStrategy(enable_escalation=False, escalation_threshold=3)
        task = TaskRecord(name="test", capability="echo", attempt=4, max_retries=3)
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=4,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False

    # NOTE: requires McManus slice 2 implementation
    @pytest.mark.xfail(reason="requires McManus slice 2: escalation_threshold on DefaultRetryStrategy", strict=False)
    def test_escalation_threshold_boundary_exactly_at_threshold(self):
        """Attempt exactly at threshold → escalate (>= is inclusive)."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=3)
        task = TaskRecord(name="test", capability="echo", attempt=3, max_retries=2)
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=3,
            max_retries=2,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True

    # NOTE: requires McManus slice 2 implementation
    @pytest.mark.xfail(reason="requires McManus slice 2: escalation_threshold on DefaultRetryStrategy", strict=False)
    def test_escalation_threshold_boundary_one_below_threshold(self):
        """Attempt one below threshold → FAILED, not escalated."""
        strategy = DefaultRetryStrategy(enable_escalation=True, escalation_threshold=3)
        task = TaskRecord(name="test", capability="echo", attempt=2, max_retries=1)
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=2,
            max_retries=1,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is False


class TestFailureContext:
    """Test FailureContext model."""

    def test_required_fields(self):
        """FailureContext should validate required fields."""
        context = FailureContext(
            task_id="test-id",
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        assert context.task_id == "test-id"
        assert context.capability == "echo"
        assert context.attempt == 1
        assert context.max_retries == 3
        assert context.error_type == "ValueError"
        assert context.error_message == "test error"

    def test_optional_fields(self):
        """FailureContext should support optional fields."""
        context = FailureContext(
            task_id="test-id",
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
            input_fingerprint="abc123",
            metadata={"source": "test"},
        )

        assert context.input_fingerprint == "abc123"
        assert context.metadata["source"] == "test"

    def test_serializable(self):
        """FailureContext should be serializable for audit trail."""
        context = FailureContext(
            task_id="test-id",
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        data = context.model_dump()
        assert isinstance(data, dict)
        assert data["task_id"] == "test-id"
        assert data["error_type"] == "ValueError"


class TestRetryDecision:
    """Test RetryDecision model."""

    def test_required_fields(self):
        """RetryDecision should validate required fields."""
        decision = RetryDecision(should_retry=True)

        assert decision.should_retry is True
        assert decision.delay_seconds is None
        assert decision.adjusted_input is None
        assert decision.reason is None
        assert decision.escalate is False

    def test_full_decision(self):
        """RetryDecision should support all optional fields."""
        decision = RetryDecision(
            should_retry=True,
            delay_seconds=5.0,
            adjusted_input={"retry": True},
            reason="Rate limit exceeded",
            escalate=False,
        )

        assert decision.should_retry is True
        assert decision.delay_seconds == 5.0
        assert decision.adjusted_input == {"retry": True}
        assert decision.reason == "Rate limit exceeded"
        assert decision.escalate is False

    def test_escalation_decision(self):
        """RetryDecision should support escalation."""
        decision = RetryDecision(
            should_retry=False,
            reason="Too many failures",
            escalate=True,
        )

        assert decision.should_retry is False
        assert decision.escalate is True
        assert decision.reason == "Too many failures"


class CustomRetryStrategy:
    """Custom strategy for testing Protocol compliance."""

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        """Never retry, always escalate."""
        return RetryDecision(
            should_retry=False,
            reason="Custom policy: no retries",
            escalate=True,
        )


class TestRetryStrategyProtocol:
    """Test that custom strategies satisfy the Protocol."""

    def test_custom_strategy_works(self):
        """Custom strategy should satisfy RetryStrategy Protocol."""
        strategy = CustomRetryStrategy()
        task = TaskRecord(
            name="test",
            capability="echo",
            attempt=1,
            max_retries=3,
        )
        failure = FailureContext(
            task_id=task.task_id,
            capability="echo",
            attempt=1,
            max_retries=3,
            error_type="ValueError",
            error_message="test error",
        )

        decision = strategy.decide(task, failure)

        assert decision.should_retry is False
        assert decision.escalate is True
        assert "Custom policy" in decision.reason
