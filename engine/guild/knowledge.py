"""Guild knowledge base — records both successes and failures for the full story.

When a task fails after max retries (or reaches ESCALATED), the failure
context is published to the guild store as a structured record keyed by
(capability + error_type + input_fingerprint).

When a task succeeds, a success record is published under the same
fingerprint pattern (with error_type="_success") so the guild accumulates
both sides: "this approach has succeeded N times and failed M times."

The knowledge base handles the lifecycle: create new records, update
existing ones with fresh metadata, and prevent unbounded growth by
enforcing a max-records limit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from engine.guild.interface import FailureFingerprint, GuildConfig, GuildRecord, GuildStore
from engine.guild.store import _compute_input_fingerprint
from engine.interfaces.retry import FailureContext

_SUCCESS_ERROR_TYPE = "_success"


def _now() -> datetime:
    return datetime.now(tz=UTC)


class FailureKnowledgeBase:
    """Publishes task outcomes (success and failure) to the guild store.

    After a task exhausts its retries or escalates, call ``publish()`` with
    the accumulated failure contexts to create or update guild records.

    After a task completes successfully, call ``publish_success()`` with the
    capability and input to create or update a success record.

    When ``config.enabled`` is False (the default), all methods are no-ops.
    This makes guild participation opt-in: a deployment handling sensitive
    data can operate fully isolated.
    """

    def __init__(
        self,
        store: GuildStore,
        config: GuildConfig | None = None,
    ) -> None:
        self._store = store
        self._config = config or GuildConfig()
        self._project = self._config.project_name

    @property
    def enabled(self) -> bool:
        """Whether guild publishing is active."""
        return self._config.enabled

    def publish(
        self,
        *,
        capability: str,
        failure_contexts: list[FailureContext],
        role: str | None = None,
        resolution_hint: str | None = None,
        approach_adjustment: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[GuildRecord]:
        """Publish failure contexts to the guild store.

        For each unique failure context (by fingerprint), create or update
        a guild record. Records with the same fingerprint accumulate
        failure counts.

        Returns the list of published/updated guild records (empty when
        guild is disabled).
        """
        if not self._config.enabled:
            return []

        published: list[GuildRecord] = []
        seen: set[str] = set()

        for ctx in failure_contexts:
            fingerprint = FailureFingerprint(
                capability=capability or ctx.capability,
                error_type=ctx.error_type,
                input_fingerprint=ctx.input_fingerprint or _compute_input_fingerprint({}),
            )

            key = fingerprint.to_key()
            if key in seen:
                # Update failure count on the already-published record
                for record in published:
                    if record.fingerprint.to_key() == key:
                        record.failure_count += 1
                        record.updated_at = _now()
                        self._store.save(record)
                continue
            seen.add(key)

            existing = self._store.get(fingerprint)
            if existing is not None:
                existing.failure_count += 1
                existing.updated_at = _now()
                if resolution_hint is not None:
                    existing.resolution_hint = resolution_hint
                if approach_adjustment is not None:
                    existing.approach_adjustment.update(approach_adjustment)
                if role is not None:
                    existing.role = role
                if self._project is not None:
                    existing.project = self._project
                self._store.save(existing)
                published.append(existing)
            else:
                record = GuildRecord(
                    fingerprint=fingerprint,
                    resolution_hint=resolution_hint,
                    approach_adjustment=dict(approach_adjustment or {}),
                    role=role,
                    project=self._project,
                    failure_count=1,
                    created_at=_now(),
                    updated_at=_now(),
                    metadata=dict(metadata or {}),
                )
                self._store.save(record)
                published.append(record)

        self._enforce_limit()
        return published

    def publish_success(
        self,
        *,
        capability: str,
        input_data: dict[str, Any],
        role: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GuildRecord | None:
        """Record a successful task outcome in the guild.

        Creates or updates a guild record keyed by
        (capability, error_type="_success", input_fingerprint).
        The success_count is incremented on each call, giving a complete
        picture of how many times this approach has worked.

        Returns the published record, or None when guild is disabled.
        """
        if not self._config.enabled:
            return None

        input_fingerprint = _compute_input_fingerprint(input_data)
        fingerprint = FailureFingerprint(
            capability=capability,
            error_type=_SUCCESS_ERROR_TYPE,
            input_fingerprint=input_fingerprint,
        )

        existing = self._store.get(fingerprint)
        if existing is not None:
            existing.success_count += 1
            existing.updated_at = _now()
            if role is not None:
                existing.role = role
            if self._project is not None:
                existing.project = self._project
            self._store.save(existing)
            self._enforce_limit()
            return existing

        record = GuildRecord(
            fingerprint=fingerprint,
            role=role,
            project=self._project,
            success_count=1,
            failure_count=0,
            created_at=_now(),
            updated_at=_now(),
            metadata=dict(metadata or {}),
        )
        self._store.save(record)
        self._enforce_limit()
        return record

    def publish_failure(
        self,
        *,
        capability: str,
        failure: FailureContext,
        role: str | None = None,
        resolution_hint: str | None = None,
        approach_adjustment: dict[str, Any] | None = None,
    ) -> GuildRecord | None:
        """Convenience: publish a single failure context to the guild.

        Returns the published record, or None when guild is disabled.
        """
        records = self.publish(
            capability=capability,
            failure_contexts=[failure],
            role=role,
            resolution_hint=resolution_hint,
            approach_adjustment=approach_adjustment,
        )
        return records[0] if records else None

    def lookup(
        self,
        *,
        capability: str,
        input_data: dict[str, Any],
        error_type: str | None = None,
    ) -> list[GuildRecord]:
        """Look up matching guild records for the given task context.

        Returns records that match on capability and (optionally) error_type.
        Used by PeerSuggestions before task execution.
        """
        if not self._config.enabled:
            return []

        return self._store.list(capability=capability, error_type=error_type)

    def _enforce_limit(self) -> None:
        """Trim oldest records when the store exceeds max_records."""
        if self._config.max_records <= 0:
            return
        all_records = self._store.list()
        if len(all_records) <= self._config.max_records:
            return
        # Remove oldest records (by created_at) until under the limit
        sorted_records = sorted(all_records, key=lambda r: r.created_at)
        to_remove = len(sorted_records) - self._config.max_records
        for record in sorted_records[:to_remove]:
            self._store.delete(record.fingerprint)
