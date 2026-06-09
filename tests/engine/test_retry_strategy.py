"""Tests for behavioral retry strategy."""


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


# ---------------------------------------------------------------------------
# ExponentialBackoffRetryStrategy
# ---------------------------------------------------------------------------


class TestExponentialBackoffRetryStrategy:
    from engine.runtime.retry import ExponentialBackoffRetryStrategy

    def _make_failure(self, *, attempt: int, max_retries: int) -> FailureContext:
        return FailureContext(
            task_id="t1",
            capability="echo",
            attempt=attempt,
            max_retries=max_retries,
            error_type="RuntimeError",
            error_message="boom",
        )

    def _make_task(self, *, attempt: int, max_retries: int) -> TaskRecord:
        return TaskRecord(name="t", capability="echo", attempt=attempt, max_retries=max_retries)

    def test_retries_while_attempts_remain(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(base_delay=1.0, multiplier=2.0, max_delay=60.0)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.should_retry is True
        assert decision.escalate is False

    def test_delay_increases_exponentially(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(base_delay=1.0, multiplier=2.0, max_delay=100.0)
        delays = [
            strategy.decide(self._make_task(attempt=a, max_retries=5), self._make_failure(attempt=a, max_retries=5)).delay_seconds
            for a in range(1, 5)
        ]
        # 1.0, 2.0, 4.0, 8.0
        assert delays == [1.0, 2.0, 4.0, 8.0]

    def test_delay_is_capped_at_max(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(base_delay=10.0, multiplier=10.0, max_delay=50.0)
        decision = strategy.decide(self._make_task(attempt=3, max_retries=5), self._make_failure(attempt=3, max_retries=5))
        assert decision.delay_seconds == 50.0

    def test_no_retry_when_exhausted(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy()
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.should_retry is False

    def test_escalates_when_enabled_and_exhausted(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(enable_escalation=True)
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.should_retry is False
        assert decision.escalate is True

    def test_no_escalation_when_disabled(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(enable_escalation=False)
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.escalate is False

    def test_escalation_threshold_gates_escalation(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(enable_escalation=True, escalation_threshold=10)
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.should_retry is False
        assert decision.escalate is False

    def test_reason_contains_delay(self) -> None:
        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        strategy = ExponentialBackoffRetryStrategy(base_delay=2.0)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert "2.00s" in decision.reason

    def test_invalid_base_delay_raises(self) -> None:
        import pytest

        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        with pytest.raises(ValueError, match="base_delay"):
            ExponentialBackoffRetryStrategy(base_delay=0)

    def test_invalid_multiplier_raises(self) -> None:
        import pytest

        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        with pytest.raises(ValueError, match="multiplier"):
            ExponentialBackoffRetryStrategy(multiplier=0.5)

    def test_max_delay_less_than_base_raises(self) -> None:
        import pytest

        from engine.runtime.retry import ExponentialBackoffRetryStrategy
        with pytest.raises(ValueError, match="max_delay"):
            ExponentialBackoffRetryStrategy(base_delay=10.0, max_delay=5.0)


# ---------------------------------------------------------------------------
# JitteredBackoffRetryStrategy
# ---------------------------------------------------------------------------


class TestJitteredBackoffRetryStrategy:
    def _make_failure(self, *, attempt: int, max_retries: int) -> FailureContext:
        return FailureContext(
            task_id="t1",
            capability="echo",
            attempt=attempt,
            max_retries=max_retries,
            error_type="RuntimeError",
            error_message="boom",
        )

    def _make_task(self, *, attempt: int, max_retries: int) -> TaskRecord:
        return TaskRecord(name="t", capability="echo", attempt=attempt, max_retries=max_retries)

    def test_retries_while_attempts_remain(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        strategy = JitteredBackoffRetryStrategy(random_fn=lambda: 0.5)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.should_retry is True

    def test_delay_is_within_expected_range(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        # random_fn=1.0 gives maximum jitter (full cap)
        strategy = JitteredBackoffRetryStrategy(base_delay=1.0, multiplier=2.0, max_delay=100.0, random_fn=lambda: 1.0)
        decision = strategy.decide(self._make_task(attempt=2, max_retries=5), self._make_failure(attempt=2, max_retries=5))
        # cap at attempt 2 = 1.0 * 2^1 = 2.0; jitter=1.0 => delay=2.0
        assert decision.delay_seconds == 2.0

    def test_zero_jitter_gives_zero_delay(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        strategy = JitteredBackoffRetryStrategy(random_fn=lambda: 0.0)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.delay_seconds == 0.0

    def test_delay_is_capped_by_max(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        # base=1, multiplier=100 -> cap at attempt 3 = 1*100^2=10000, clamped to max_delay=30
        # random_fn=1.0 -> delay = 1.0 * 30 = 30.0
        strategy = JitteredBackoffRetryStrategy(base_delay=1.0, multiplier=100.0, max_delay=30.0, random_fn=lambda: 1.0)
        decision = strategy.decide(self._make_task(attempt=3, max_retries=5), self._make_failure(attempt=3, max_retries=5))
        assert decision.delay_seconds <= 30.0

    def test_no_retry_when_exhausted(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        strategy = JitteredBackoffRetryStrategy(random_fn=lambda: 0.5)
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.should_retry is False

    def test_escalates_when_enabled(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        strategy = JitteredBackoffRetryStrategy(enable_escalation=True, random_fn=lambda: 0.5)
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.escalate is True

    def test_reason_mentions_jitter(self) -> None:
        from engine.runtime.retry import JitteredBackoffRetryStrategy
        strategy = JitteredBackoffRetryStrategy(random_fn=lambda: 0.5)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert "jittered" in decision.reason


# ---------------------------------------------------------------------------
# InputAdjustingRetryStrategy
# ---------------------------------------------------------------------------


class TestInputAdjustingRetryStrategy:
    def _make_failure(self, *, attempt: int, max_retries: int) -> FailureContext:
        return FailureContext(
            task_id="t1",
            capability="echo",
            attempt=attempt,
            max_retries=max_retries,
            error_type="RuntimeError",
            error_message="boom",
        )

    def _make_task(self, *, attempt: int, max_retries: int) -> TaskRecord:
        return TaskRecord(name="t", capability="echo", attempt=attempt, max_retries=max_retries)

    def test_adjusted_input_is_set(self) -> None:
        from engine.runtime.retry import InputAdjustingRetryStrategy
        strategy = InputAdjustingRetryStrategy(adjuster=lambda ctx: {"attempt": ctx.attempt})
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.should_retry is True
        assert decision.adjusted_input == {"attempt": 1}

    def test_none_adjuster_result_passes_through(self) -> None:
        from engine.runtime.retry import InputAdjustingRetryStrategy
        strategy = InputAdjustingRetryStrategy(adjuster=lambda ctx: None)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.should_retry is True
        assert decision.adjusted_input is None

    def test_no_delay_without_base_strategy(self) -> None:
        from engine.runtime.retry import InputAdjustingRetryStrategy
        strategy = InputAdjustingRetryStrategy(adjuster=lambda ctx: {})
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.delay_seconds is None

    def test_uses_delay_from_base_strategy(self) -> None:
        from engine.runtime.retry import (
            ExponentialBackoffRetryStrategy,
            InputAdjustingRetryStrategy,
        )
        base = ExponentialBackoffRetryStrategy(base_delay=5.0, multiplier=1.0, max_delay=100.0)
        strategy = InputAdjustingRetryStrategy(adjuster=lambda ctx: {"retry": True}, base=base)
        decision = strategy.decide(self._make_task(attempt=1, max_retries=3), self._make_failure(attempt=1, max_retries=3))
        assert decision.delay_seconds == 5.0
        assert decision.adjusted_input == {"retry": True}

    def test_no_retry_when_exhausted(self) -> None:
        from engine.runtime.retry import InputAdjustingRetryStrategy
        strategy = InputAdjustingRetryStrategy(adjuster=lambda ctx: {})
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.should_retry is False

    def test_escalates_when_enabled(self) -> None:
        from engine.runtime.retry import InputAdjustingRetryStrategy
        strategy = InputAdjustingRetryStrategy(adjuster=lambda ctx: {}, enable_escalation=True)
        decision = strategy.decide(self._make_task(attempt=4, max_retries=3), self._make_failure(attempt=4, max_retries=3))
        assert decision.escalate is True

    def test_adjuster_receives_full_failure_context(self) -> None:
        from engine.runtime.retry import InputAdjustingRetryStrategy
        captured: list[FailureContext] = []
        def adjuster(ctx: FailureContext) -> dict:
            captured.append(ctx)
            return {}
        strategy = InputAdjustingRetryStrategy(adjuster=adjuster)
        failure = self._make_failure(attempt=2, max_retries=5)
        strategy.decide(self._make_task(attempt=2, max_retries=5), failure)
        assert len(captured) == 1
        assert captured[0].attempt == 2
        assert captured[0].error_type == "RuntimeError"
