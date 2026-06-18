"""Peer suggestion engine — checks the guild before task execution.

Before a task executes, the peer suggestion engine queries the guild store
for fingerprints that match the current task context (capability + error_type
+ input fingerprint). Matching records are returned as GuildSuggestion objects
with confidence scores, allowing the supervisor to apply approach adjustments
or skip suggestions that are not relevant.

Role-scoped knowledge: when a role is specified (e.g. "worker"), the engine
prefers suggestions from the same role, boosting their confidence scores.
"""

from __future__ import annotations

from typing import Any

from engine.guild.interface import (
    GuildConfig,
    GuildStore,
    GuildSuggestion,
)
from engine.guild.store import _compute_input_fingerprint


class DefaultPeerSuggestionEngine:
    """Default peer suggestion engine.

    Queries the guild store for records matching the task capability and
    computes a confidence score based on input fingerprint similarity,
    error type match, and role match.

    When ``config.enabled`` is False (the default), ``suggest()`` always
    returns an empty list.
    """

    def __init__(
        self,
        store: GuildStore,
        config: GuildConfig | None = None,
    ) -> None:
        self._store = store
        self._config = config or GuildConfig()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def suggest(
        self,
        *,
        capability: str,
        input_data: dict[str, Any],
        role: str | None = None,
    ) -> list[GuildSuggestion]:
        """Return matching suggestions from the guild for the given task context.

        Returns both failure warnings and success guidance. Success records
        (error_type="_success") indicate approaches that have worked before
        and their approach_adjustments capture what made them work.

        Confidence scoring:
            - Base 0.5 for any capability match
            - +0.3 if the input fingerprint matches exactly (same input shape
              as a known success or failure)
            - +0.2 if the requesting role matches the stored role (role-scoped
              knowledge bonus)
            - Results sorted by descending confidence
        """
        if not self._config.enabled:
            return []

        records = self._store.list(capability=capability)
        if not records:
            return []

        input_fp = _compute_input_fingerprint(input_data)
        suggestions: list[GuildSuggestion] = []

        for record in records:
            confidence = 0.5  # base: capability match

            # Exact input fingerprint match → higher confidence
            if record.fingerprint.input_fingerprint == input_fp:
                confidence += 0.3

            # Role match bonus (role-scoped knowledge)
            if role is not None and record.role == role:
                confidence += 0.2

            suggestions.append(
                GuildSuggestion(
                    fingerprint=record.fingerprint,
                    resolution_hint=record.resolution_hint,
                    approach_adjustment=dict(record.approach_adjustment),
                    source_role=record.role,
                    source_project=record.project,
                    confidence=min(confidence, 1.0),
                )
            )

        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions
