"""Guild layer — cross-project failure learning and role-scoped knowledge sharing.

The guild is an opt-in structured data layer that lets agent roles share
knowledge about failures and resolutions across projects.

Key components:
    - FailureKnowledgeBase: publishes successes and failures after tasks finish
    - PeerSuggestions: checks the guild before task execution for known patterns
    - GuildMeetingService: periodic cross-role knowledge consolidation ("guild meetings")
    - Role-scoped knowledge: worker roles share learnings across projects
    - Edge Events catalog: shared lifecycle event vocabulary for all agents
    - GuildStore: persistence backend for guild records
"""

from engine.guild.interface import (
    FailureFingerprint,
    GuildConfig,
    GuildRecord,
    GuildStore,
    GuildSuggestion,
    PeerSuggestionEngine,
)
from engine.guild.knowledge import FailureKnowledgeBase
from engine.guild.meeting import (
    CapabilityProfile,
    CrossRoleInsight,
    GuildMeetingReport,
    GuildMeetingService,
    RoleKnowledgeDigest,
)
from engine.guild.peer import DefaultPeerSuggestionEngine
from engine.guild.store import (
    GuildRecordNotFoundError,
    LocalGuildStore,
    MemoryGuildStore,
)

__all__ = [
    "CapabilityProfile",
    "CrossRoleInsight",
    "DefaultPeerSuggestionEngine",
    "FailureFingerprint",
    "FailureKnowledgeBase",
    "GuildConfig",
    "GuildMeetingReport",
    "GuildMeetingService",
    "GuildRecord",
    "GuildRecordNotFoundError",
    "GuildStore",
    "GuildSuggestion",
    "LocalGuildStore",
    "MemoryGuildStore",
    "PeerSuggestionEngine",
    "RoleKnowledgeDigest",
]
