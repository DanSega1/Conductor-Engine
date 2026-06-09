"""Retry strategy implementations."""

from __future__ import annotations

from collections.abc import Callable
import random as _random
from typing import TYPE_CHECKING, Any

from engine.interfaces.retry import FailureContext, RetryDecision

if TYPE_CHECKING:
    from engine.interfaces.task import TaskRecord


class DefaultRetryStrategy:
    """Retry while attempts remain; optionally escalate when exhausted.

    Preserves existing supervisor behavior:
    - Retry if attempt <= max_retries
    - No input adjustment (same input for every retry)
    - No delay between retries
    - Escalation is opt-in via enable_escalation flag

    escalation_threshold:
        When set alongside enable_escalation=True, escalation only triggers
        once failure.attempt >= escalation_threshold. Attempts below the
        threshold still produce a plain FAILED outcome rather than ESCALATED.
        When None (default), any exhaustion triggers escalation (if enabled).
    """

    def __init__(
        self,
        *,
        enable_escalation: bool = False,
        escalation_threshold: int | None = None,
    ) -> None:
        self.enable_escalation = enable_escalation
        self.escalation_threshold = escalation_threshold

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        """Decide retry based on attempt count and escalation config."""
        if failure.attempt > failure.max_retries:
            should_escalate = self.enable_escalation and (
                self.escalation_threshold is None
                or failure.attempt >= self.escalation_threshold
            )
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=should_escalate,
            )
        return RetryDecision(
            should_retry=True,
            reason=f"Retry {failure.attempt} of {failure.max_retries}",
        )


class ExponentialBackoffRetryStrategy:
    """Retry with exponentially increasing delays between attempts.

    Each retry waits ``base_delay * (multiplier ** (attempt - 1))`` seconds,
    capped at ``max_delay``.  Escalation is opt-in.

    Example — 1 s, 2 s, 4 s, 8 s (base=1, multiplier=2):

        strategy = ExponentialBackoffRetryStrategy(
            base_delay=1.0, multiplier=2.0, max_delay=30.0
        )
    """

    def __init__(
        self,
        *,
        base_delay: float = 1.0,
        multiplier: float = 2.0,
        max_delay: float = 60.0,
        enable_escalation: bool = False,
        escalation_threshold: int | None = None,
    ) -> None:
        if base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if multiplier < 1.0:
            raise ValueError("multiplier must be >= 1.0")
        if max_delay < base_delay:
            raise ValueError("max_delay must be >= base_delay")

        self.base_delay = base_delay
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.enable_escalation = enable_escalation
        self.escalation_threshold = escalation_threshold

    def _compute_delay(self, attempt: int) -> float:
        raw = self.base_delay * (self.multiplier ** (attempt - 1))
        return min(raw, self.max_delay)

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        if failure.attempt > failure.max_retries:
            should_escalate = self.enable_escalation and (
                self.escalation_threshold is None
                or failure.attempt >= self.escalation_threshold
            )
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=should_escalate,
            )
        delay = self._compute_delay(failure.attempt)
        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            reason=f"Retry {failure.attempt} of {failure.max_retries} after {delay:.2f}s",
        )


class JitteredBackoffRetryStrategy:
    """Exponential backoff with full jitter to spread out retry storms.

    Delay is drawn uniformly from ``[0, base_delay * multiplier^(attempt-1)]``
    then capped at ``max_delay``.  This is the "full jitter" algorithm from
    the AWS exponential backoff blog post — it prevents coordinated retry
    spikes across many concurrent workers.

    Pass ``random_fn`` in tests to make behaviour deterministic.
    """

    def __init__(
        self,
        *,
        base_delay: float = 1.0,
        multiplier: float = 2.0,
        max_delay: float = 60.0,
        enable_escalation: bool = False,
        escalation_threshold: int | None = None,
        random_fn: Callable[[], float] = _random.random,
    ) -> None:
        if base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if multiplier < 1.0:
            raise ValueError("multiplier must be >= 1.0")
        if max_delay < base_delay:
            raise ValueError("max_delay must be >= base_delay")

        self.base_delay = base_delay
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.enable_escalation = enable_escalation
        self.escalation_threshold = escalation_threshold
        self._random_fn = random_fn

    def _compute_delay(self, attempt: int) -> float:
        cap = min(self.base_delay * (self.multiplier ** (attempt - 1)), self.max_delay)
        return self._random_fn() * cap

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        if failure.attempt > failure.max_retries:
            should_escalate = self.enable_escalation and (
                self.escalation_threshold is None
                or failure.attempt >= self.escalation_threshold
            )
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=should_escalate,
            )
        delay = self._compute_delay(failure.attempt)
        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            reason=f"Retry {failure.attempt} of {failure.max_retries} after {delay:.3f}s (jittered)",
        )


class InputAdjustingRetryStrategy:
    """Retry with per-attempt input adjustment driven by a caller-supplied function.

    Demonstrates the ``adjusted_input`` path on ``RetryDecision``.  On each
    retry the ``adjuster`` receives the current ``FailureContext`` and returns
    a replacement input dict that the supervisor will use instead of the
    original task input.  Returning ``None`` keeps the original input unchanged.

    This strategy can be composed with backoff by wrapping it:

        base = ExponentialBackoffRetryStrategy(base_delay=2.0)

        def adjuster(ctx: FailureContext) -> dict | None:
            return {"retry_hint": ctx.attempt}

        strategy = InputAdjustingRetryStrategy(adjuster=adjuster, base=base)

    When ``base`` is None a flat retry (no delay) is used.
    """

    def __init__(
        self,
        *,
        adjuster: Callable[[FailureContext], dict[str, Any] | None],
        base: Any | None = None,
        enable_escalation: bool = False,
        escalation_threshold: int | None = None,
    ) -> None:
        self._adjuster = adjuster
        self._base = base
        self.enable_escalation = enable_escalation
        self.escalation_threshold = escalation_threshold

    def decide(self, task: TaskRecord, failure: FailureContext) -> RetryDecision:
        if failure.attempt > failure.max_retries:
            should_escalate = self.enable_escalation and (
                self.escalation_threshold is None
                or failure.attempt >= self.escalation_threshold
            )
            return RetryDecision(
                should_retry=False,
                reason="Retry attempts exhausted",
                escalate=should_escalate,
            )

        # Delegate delay logic to the wrapped base strategy if one was provided.
        if self._base is not None:
            base_decision = self._base.decide(task, failure)
            delay = base_decision.delay_seconds
            reason = base_decision.reason
        else:
            delay = None
            reason = f"Retry {failure.attempt} of {failure.max_retries} (adjusted input)"

        adjusted = self._adjuster(failure)
        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            adjusted_input=adjusted,
            reason=reason,
        )
