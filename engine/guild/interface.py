"""Guild layer contracts — models and protocols for cross-project failure learning.

The guild is a structured data layer that stores failure fingerprints
(resolution hints keyed by capability + error type + input shape) and
enables peer suggestions before task execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Core value types
# ---------------------------------------------------------------------------


class FailureFingerprint(BaseModel):
    """Stable key for guild lookups.

    Composed from the aspects of a failed task that are most useful for
    matching across projects: the capability name, the error type, and a
    fingerprint of the input shape (typically a hash prefix).
    """

    capability: str
    error_type: str
    input_fingerprint: str

    def to_key(self) -> str:
        """Return a deterministic string key for this fingerprint."""
        return f"{self.capability}:{self.error_type}:{self.input_fingerprint}"


class GuildRecord(BaseModel):
    """A stored knowledge entry in the guild.

    Published when a task fails after max retries and can be queried by
    peer suggestion engines before subsequent task execution.
    """

    fingerprint: FailureFingerprint
    resolution_hint: str | None = None
    approach_adjustment: dict[str, Any] = Field(default_factory=dict)
    role: str | None = None
    project: str | None = None
    success_count: int = 0
    failure_count: int = 1
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuildSuggestion(BaseModel):
    """A resolution hint returned by a peer suggestion engine.

    Returned before a task executes if the guild contains a matching
    fingerprint. The caller can apply the approach_adjustment to the
    task input or skip suggestions that are not relevant.
    """

    fingerprint: FailureFingerprint
    resolution_hint: str | None = None
    approach_adjustment: dict[str, Any] = Field(default_factory=dict)
    source_role: str | None = None
    source_project: str | None = None
    confidence: float = 0.0  # 0.0 (guessing) to 1.0 (exact match)


class GuildConfig(BaseModel):
    """Configuration for guild participation.

    Guild is opt-in per deployment. When enabled, the runtime publishes
    failure records and checks for peer suggestions. Disabled by default.
    """

    enabled: bool = False
    store_path: str | None = None
    project_name: str | None = None
    max_records: int = 1000


# ---------------------------------------------------------------------------
# GuildStore protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class GuildStore(Protocol):
    """Persistence contract for guild knowledge records.

    Implementations store FailureFingerprint → GuildRecord mappings.
    All reads return deep copies.
    """

    def save(self, record: GuildRecord) -> GuildRecord:
        """Persist a guild record."""
        ...

    def get(self, fingerprint: FailureFingerprint) -> GuildRecord | None:
        """Return the guild record for a fingerprint, if present."""
        ...

    def list(
        self,
        *,
        capability: str | None = None,
        error_type: str | None = None,
        role: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GuildRecord]:
        """Return stored guild records, optionally filtered."""
        ...

    def delete(self, fingerprint: FailureFingerprint) -> bool:
        """Remove a guild record. Returns True if deleted."""
        ...

    def clear(self) -> None:
        """Remove all guild records."""
        ...


# ---------------------------------------------------------------------------
# PeerSuggestionEngine protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PeerSuggestionEngine(Protocol):
    """Contract for checking the guild before task execution.

    Implementations query the guild store for fingerprints that match
    the current task context and return suggestions with confidence scores.
    """

    def suggest(
        self,
        *,
        capability: str,
        input_data: dict[str, Any],
        role: str | None = None,
    ) -> list[GuildSuggestion]:
        """Return matching suggestions from the guild for the given task context."""
        ...
