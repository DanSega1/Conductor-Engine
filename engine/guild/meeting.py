"""Guild meeting service — periodic cross-role knowledge consolidation.

A "guild meeting" is a process where the guild reviews its accumulated
knowledge (successes and failures) across all agent roles and produces
insights. This mimics a real guild where members sit together and learn
from each other's experiences.

The meeting:
    1. Reads all guild records
    2. Groups knowledge by role (planner, worker, validator) and by capability
    3. Identifies trends: most common failures, most reliable capabilities,
       success/failure ratios per capability
    4. Produces cross-role insights: patterns that span multiple roles
    5. Generates a GuildMeetingReport that can be logged, displayed, or
       published as an event

The meeting is opt-in (respects GuildConfig.enabled) and can be triggered
on-demand via the CLI (``cond guild meet``) or scheduled periodically
using the existing cron trigger infrastructure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from engine.guild.interface import GuildConfig, GuildRecord, GuildStore

_SUCCESS_ERROR_TYPE = "_success"


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Meeting report model
# ---------------------------------------------------------------------------


class CapabilityProfile(BaseModel):
    """Knowledge profile for a single capability, aggregated across roles."""

    capability: str
    total_successes: int = 0
    total_failures: int = 0
    distinct_error_types: list[str] = []
    roles: list[str] = []
    top_failures: list[dict[str, Any]] = []
    top_successes: list[dict[str, Any]] = []


class RoleKnowledgeDigest(BaseModel):
    """Summary of what a specific agent role has learned."""

    role: str
    total_records: int = 0
    capabilities_encountered: list[str] = []
    top_failure_patterns: list[dict[str, Any]] = []
    top_success_patterns: list[dict[str, Any]] = []


class CrossRoleInsight(BaseModel):
    """A pattern or trend that spans multiple agent roles."""

    description: str
    capabilities: list[str] = []
    roles: list[str] = []
    severity: str = "info"  # info, warning, critical


class GuildMeetingReport(BaseModel):
    """Output of a guild meeting — structured knowledge summary."""

    meeting_id: str = ""
    held_at: datetime = Field(default_factory=_now)
    total_records: int = 0
    roles_present: list[str] = []
    capability_profiles: list[CapabilityProfile] = []
    role_digests: list[RoleKnowledgeDigest] = []
    cross_role_insights: list[CrossRoleInsight] = []
    summary: str = ""


# ---------------------------------------------------------------------------
# Meeting service
# ---------------------------------------------------------------------------


class GuildMeetingService:
    """Periodic or on-demand guild knowledge consolidation.

    Reads all guild records, groups by role and capability, computes
    success/failure ratios, and produces cross-role insights.

    When ``config.enabled`` is False, ``hold_meeting()`` returns None.
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

    def hold_meeting(self) -> GuildMeetingReport | None:
        """Run a guild meeting and return the consolidated report.

        Returns None when guild is disabled. The report contains per-role
        knowledge digests, per-capability profiles, and cross-role insights.
        """
        if not self._config.enabled:
            return None

        all_records = self._store.list()
        if not all_records:
            return GuildMeetingReport(
                meeting_id=_now().isoformat(),
                summary="No guild records to review. The guild is empty.",
            )

        # Group by role
        by_role: dict[str, list[GuildRecord]] = {}
        for record in all_records:
            role = record.role or "unassigned"
            by_role.setdefault(role, []).append(record)

        # Group by capability
        by_capability: dict[str, list[GuildRecord]] = {}
        for record in all_records:
            cap = record.fingerprint.capability
            by_capability.setdefault(cap, []).append(record)

        # Build per-capability profiles
        capability_profiles: list[CapabilityProfile] = []
        for cap, records in sorted(by_capability.items()):
            successes = sum(r.success_count for r in records)
            failures = sum(r.failure_count for r in records)
            error_types = sorted({
                r.fingerprint.error_type
                for r in records
                if r.fingerprint.error_type != _SUCCESS_ERROR_TYPE
            })
            roles = sorted({r.role for r in records if r.role})

            top_failures = sorted(
                [r for r in records if r.fingerprint.error_type != _SUCCESS_ERROR_TYPE],
                key=lambda r: r.failure_count,
                reverse=True,
            )[:3]
            top_successes = sorted(
                [r for r in records if r.fingerprint.error_type == _SUCCESS_ERROR_TYPE],
                key=lambda r: r.success_count,
                reverse=True,
            )[:3]

            capability_profiles.append(CapabilityProfile(
                capability=cap,
                total_successes=successes,
                total_failures=failures,
                distinct_error_types=error_types,
                roles=roles,
                top_failures=[
                    {
                        "error_type": r.fingerprint.error_type,
                        "input_fingerprint": r.fingerprint.input_fingerprint,
                        "count": r.failure_count,
                        "hint": r.resolution_hint,
                    }
                    for r in top_failures
                ],
                top_successes=[
                    {
                        "input_fingerprint": r.fingerprint.input_fingerprint,
                        "count": r.success_count,
                        "adjustment": r.approach_adjustment,
                    }
                    for r in top_successes
                ],
            ))

        # Build per-role knowledge digests
        role_digests: list[RoleKnowledgeDigest] = []
        for role, records in sorted(by_role.items()):
            if role == "unassigned":
                continue
            caps = sorted({r.fingerprint.capability for r in records})
            failure_patterns = sorted(
                [r for r in records if r.fingerprint.error_type != _SUCCESS_ERROR_TYPE],
                key=lambda r: r.failure_count,
                reverse=True,
            )[:5]
            success_patterns = sorted(
                [r for r in records if r.fingerprint.error_type == _SUCCESS_ERROR_TYPE],
                key=lambda r: r.success_count,
                reverse=True,
            )[:5]

            role_digests.append(RoleKnowledgeDigest(
                role=role,
                total_records=len(records),
                capabilities_encountered=caps,
                top_failure_patterns=[
                    {
                        "capability": r.fingerprint.capability,
                        "error_type": r.fingerprint.error_type,
                        "count": r.failure_count,
                        "hint": r.resolution_hint,
                    }
                    for r in failure_patterns
                ],
                top_success_patterns=[
                    {
                        "capability": r.fingerprint.capability,
                        "input_fingerprint": r.fingerprint.input_fingerprint,
                        "count": r.success_count,
                    }
                    for r in success_patterns
                ],
            ))

        # Generate cross-role insights
        cross_role_insights: list[CrossRoleInsight] = []
        # Insight 1: capability that spans the most roles
        multi_role_caps = sorted(
            by_capability.items(),
            key=lambda item: len({r.role for r in item[1] if r.role}),
            reverse=True,
        )
        if multi_role_caps:
            top_cap, top_records = multi_role_caps[0]
            roles_using = {r.role for r in top_records if r.role}
            if len(roles_using) > 1:
                cross_role_insights.append(CrossRoleInsight(
                    description=(
                        f"Capability '{top_cap}' is used across {len(roles_using)} roles: "
                        f"{', '.join(sorted(roles_using))}. "
                        "Knowledge about this capability benefits the widest audience."
                    ),
                    capabilities=[top_cap],
                    roles=sorted(roles_using),
                    severity="info",
                ))

        # Insight 2: capability with worst success/failure ratio
        for cap, records in by_capability.items():
            total_success = sum(r.success_count for r in records)
            total_failure = sum(r.failure_count for r in records)
            total = total_success + total_failure
            if total >= 5 and total_failure > total_success:
                failure_rate = total_failure / total * 100
                cross_role_insights.append(CrossRoleInsight(
                    description=(
                        f"Capability '{cap}' has a {failure_rate:.0f}% failure rate "
                        f"({total_failure} failures in {total} attempts). "
                        "Consider reviewing inputs or approach adjustments."
                    ),
                    capabilities=[cap],
                    roles=sorted({r.role for r in records if r.role}),
                    severity="warning" if failure_rate > 75 else "info",
                ))

        # Insight 3: capability with best success/failure ratio
        for cap, records in by_capability.items():
            total_success = sum(r.success_count for r in records)
            total_failure = sum(r.failure_count for r in records)
            total = total_success + total_failure
            if total >= 5 and total_success > total_failure * 3:
                success_rate = total_success / total * 100
                cross_role_insights.append(CrossRoleInsight(
                    description=(
                        f"Capability '{cap}' has a {success_rate:.0f}% success rate "
                        f"({total_success} successes in {total} attempts). "
                        "Approach adjustments for this capability are well-established."
                    ),
                    capabilities=[cap],
                    roles=sorted({r.role for r in records if r.role}),
                    severity="info",
                ))

        # Build summary
        total_successes = sum(r.success_count for r in all_records)
        total_failures = sum(r.failure_count for r in all_records)
        roles_present = sorted(r for r in by_role if r != "unassigned")
        summary_parts = [
            f"Guild meeting held at {_now().isoformat()}.",
            f"Reviewed {len(all_records)} knowledge records across {len(roles_present)} role(s).",
            f"Total tracked: {total_successes} successes, {total_failures} failures.",
        ]
        if cross_role_insights:
            warnings = sum(1 for i in cross_role_insights if i.severity == "warning")
            if warnings:
                summary_parts.append(f"{warnings} warning(s) detected — see cross-role insights.")
        summary_parts.append(
            "Next meeting: run 'cond guild meet' or schedule via cron trigger."
        )

        return GuildMeetingReport(
            meeting_id=_now().isoformat(),
            total_records=len(all_records),
            roles_present=roles_present,
            capability_profiles=capability_profiles,
            role_digests=role_digests,
            cross_role_insights=cross_role_insights,
            summary=" ".join(summary_parts),
        )
