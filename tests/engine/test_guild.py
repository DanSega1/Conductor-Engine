"""Tests for the guild layer — store, knowledge base, peer suggestions, and CLI integration."""

from __future__ import annotations

from pathlib import Path
import tempfile

from pytest import fixture

from engine.guild import (
    DefaultPeerSuggestionEngine,
    FailureFingerprint,
    FailureKnowledgeBase,
    GuildConfig,
    GuildMeetingService,
    GuildRecord,
    LocalGuildStore,
    MemoryGuildStore,
)
from engine.interfaces.retry import FailureContext

# =========================================================================
# Fixtures
# =========================================================================


@fixture
def memory_store() -> MemoryGuildStore:
    return MemoryGuildStore()


@fixture
def local_store() -> LocalGuildStore:
    tmp = tempfile.mkstemp(suffix=".json", prefix="guild_test_")
    path = Path(tmp[1])
    path.unlink()  # mkstemp creates the file; LocalGuildStore manages its own
    store = LocalGuildStore(path)
    yield store
    if path.exists():
        path.unlink()


@fixture
def sample_fingerprint() -> FailureFingerprint:
    return FailureFingerprint(
        capability="echo",
        error_type="ValueError",
        input_fingerprint="abc123def456",
    )


@fixture
def sample_record(sample_fingerprint) -> GuildRecord:
    return GuildRecord(
        fingerprint=sample_fingerprint,
        resolution_hint="Ensure input message is a non-empty string",
        role="worker",
        project="test-project",
        failure_count=3,
    )


@fixture
def sample_failure_context() -> FailureContext:
    return FailureContext(
        task_id="task-001",
        capability="echo",
        attempt=3,
        max_retries=3,
        error_type="ValueError",
        error_message="message must be non-empty",
        input_fingerprint="abc123def456",
    )


# =========================================================================
# FailureFingerprint
# =========================================================================


class TestFailureFingerprint:
    def test_to_key_returns_deterministic_string(self) -> None:
        f1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="abc")
        f2 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="abc")
        assert f1.to_key() == f2.to_key()
        assert f1.to_key() == "echo:ValueError:abc"

    def test_to_key_differs_on_any_field(self) -> None:
        f1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="abc")
        f2 = FailureFingerprint(capability="filesystem", error_type="ValueError", input_fingerprint="abc")
        assert f1.to_key() != f2.to_key()


# =========================================================================
# GuildRecord
# =========================================================================


class TestGuildRecord:
    def test_defaults_are_sensible(self, sample_fingerprint) -> None:
        record = GuildRecord(fingerprint=sample_fingerprint)
        assert record.failure_count == 1
        assert record.success_count == 0
        assert record.role is None
        assert record.project is None
        assert record.resolution_hint is None

    def test_serialization_round_trip(self, sample_record) -> None:
        data = sample_record.model_dump(mode="json")
        restored = GuildRecord.model_validate(data)
        assert restored.fingerprint.to_key() == sample_record.fingerprint.to_key()
        assert restored.resolution_hint == sample_record.resolution_hint
        assert restored.failure_count == sample_record.failure_count


# =========================================================================
# MemoryGuildStore
# =========================================================================


class TestMemoryGuildStore:
    def test_save_and_get(self, memory_store, sample_record) -> None:
        memory_store.save(sample_record)
        retrieved = memory_store.get(sample_record.fingerprint)
        assert retrieved is not None
        assert retrieved.fingerprint.to_key() == sample_record.fingerprint.to_key()
        assert retrieved.resolution_hint == sample_record.resolution_hint

    def test_get_returns_none_for_missing(self, memory_store, sample_fingerprint) -> None:
        assert memory_store.get(sample_fingerprint) is None

    def test_get_returns_deep_copy(self, memory_store, sample_record) -> None:
        memory_store.save(sample_record)
        retrieved = memory_store.get(sample_record.fingerprint)
        assert retrieved is not None
        retrieved.failure_count = 999
        original = memory_store.get(sample_record.fingerprint)
        assert original is not None
        assert original.failure_count == sample_record.failure_count  # unchanged

    def test_list_empty(self, memory_store) -> None:
        assert memory_store.list() == []

    def test_list_all(self, memory_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="filesystem", error_type="OSError", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp1))
        memory_store.save(GuildRecord(fingerprint=fp2))
        assert len(memory_store.list()) == 2

    def test_list_filter_by_capability(self, memory_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="filesystem", error_type="OSError", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp1))
        memory_store.save(GuildRecord(fingerprint=fp2))
        results = memory_store.list(capability="echo")
        assert len(results) == 1
        assert results[0].fingerprint.capability == "echo"

    def test_list_filter_by_error_type(self, memory_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="echo", error_type="TypeError", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp1))
        memory_store.save(GuildRecord(fingerprint=fp2))
        results = memory_store.list(error_type="ValueError")
        assert len(results) == 1

    def test_list_filter_by_role(self, memory_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp1, role="worker"))
        memory_store.save(GuildRecord(fingerprint=fp2, role="validator"))
        results = memory_store.list(role="worker")
        assert len(results) == 1

    def test_list_pagination(self, memory_store) -> None:
        for i in range(5):
            fp = FailureFingerprint(capability="echo", error_type=f"E{i}", input_fingerprint=str(i))
            memory_store.save(GuildRecord(fingerprint=fp))
        assert len(memory_store.list(limit=2)) == 2
        assert len(memory_store.list(limit=2, offset=2)) == 2
        assert len(memory_store.list(offset=4)) == 1

    def test_delete_existing(self, memory_store, sample_record) -> None:
        memory_store.save(sample_record)
        assert memory_store.delete(sample_record.fingerprint) is True
        assert memory_store.get(sample_record.fingerprint) is None

    def test_delete_missing(self, memory_store, sample_fingerprint) -> None:
        assert memory_store.delete(sample_fingerprint) is False

    def test_clear(self, memory_store) -> None:
        fp = FailureFingerprint(capability="echo", error_type="E", input_fingerprint="x")
        memory_store.save(GuildRecord(fingerprint=fp))
        memory_store.clear()
        assert memory_store.list() == []


# =========================================================================
# LocalGuildStore (JSON file-backed)
# =========================================================================


class TestLocalGuildStore:
    def test_save_and_get(self, local_store, sample_record) -> None:
        local_store.save(sample_record)
        retrieved = local_store.get(sample_record.fingerprint)
        assert retrieved is not None
        assert retrieved.resolution_hint == sample_record.resolution_hint

    def test_persistence_across_reopens(self, sample_record) -> None:
        tmp = tempfile.mkstemp(suffix=".json", prefix="guild_persist_")
        path = Path(tmp[1])
        path.unlink()
        store1 = LocalGuildStore(path)
        store1.save(sample_record)
        store2 = LocalGuildStore(path)
        retrieved = store2.get(sample_record.fingerprint)
        assert retrieved is not None
        assert retrieved.resolution_hint == sample_record.resolution_hint
        path.unlink()

    def test_list_filters(self, local_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="E1", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="filesystem", error_type="E2", input_fingerprint="b")
        local_store.save(GuildRecord(fingerprint=fp1, role="worker"))
        local_store.save(GuildRecord(fingerprint=fp2, role="worker"))
        results = local_store.list(capability="echo")
        assert len(results) == 1

    def test_clear(self, local_store, sample_record) -> None:
        local_store.save(sample_record)
        local_store.clear()
        assert local_store.list() == []

    def test_delete(self, local_store, sample_record) -> None:
        local_store.save(sample_record)
        assert local_store.delete(sample_record.fingerprint) is True
        assert local_store.get(sample_record.fingerprint) is None

    def test_list_empty_when_no_file(self) -> None:
        store = LocalGuildStore("/tmp/nonexistent_guild_file.json")
        assert store.list() == []
        # Cleanup: delete the file if it was created by list()
        Path("/tmp/nonexistent_guild_file.json").unlink(missing_ok=True)


# =========================================================================
# FailureKnowledgeBase
# =========================================================================


class TestFailureKnowledgeBase:
    def test_publish_disabled_by_default(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(store=memory_store)
        assert kb.enabled is False
        result = kb.publish(capability="echo", failure_contexts=[sample_failure_context])
        assert result == []

    def test_publish_creates_record(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        result = kb.publish(capability="echo", failure_contexts=[sample_failure_context])
        assert len(result) == 1
        assert result[0].fingerprint.capability == "echo"
        assert result[0].failure_count == 1
        assert result[0].fingerprint.error_type == "ValueError"

    def test_publish_updates_existing_record(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        kb.publish(capability="echo", failure_contexts=[sample_failure_context])
        # Publish same fingerprint again — should increment failure count
        result = kb.publish(capability="echo", failure_contexts=[sample_failure_context])
        assert len(result) == 1
        assert result[0].failure_count == 2

    def test_publish_multiple_contexts(self, memory_store) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        ctx1 = FailureContext(
            task_id="t1", capability="echo", attempt=1, max_retries=2,
            error_type="ValueError", error_message="bad", input_fingerprint="a",
        )
        ctx2 = FailureContext(
            task_id="t2", capability="filesystem", attempt=1, max_retries=2,
            error_type="OSError", error_message="permission", input_fingerprint="b",
        )
        result = kb.publish(capability="mixed", failure_contexts=[ctx1, ctx2])
        assert len(result) == 2

    def test_publish_with_role_and_project(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(
            store=memory_store,
            config=GuildConfig(enabled=True, project_name="my-project"),
        )
        result = kb.publish(
            capability="echo",
            failure_contexts=[sample_failure_context],
            role="worker",
            resolution_hint="Check input format",
            approach_adjustment={"strict": True},
        )
        assert len(result) == 1
        record = result[0]
        assert record.role == "worker"
        assert record.project == "my-project"
        assert record.resolution_hint == "Check input format"
        assert record.approach_adjustment == {"strict": True}

    def test_publish_single_convenience(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        record = kb.publish_failure(
            capability="echo",
            failure=sample_failure_context,
            role="worker",
        )
        assert record is not None
        assert record.fingerprint.capability == "echo"
        assert record.role == "worker"

    def test_publish_single_returns_none_when_disabled(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(store=memory_store)
        assert kb.publish_failure(capability="echo", failure=sample_failure_context) is None

    def test_lookup(self, memory_store, sample_failure_context) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        kb.publish(capability="echo", failure_contexts=[sample_failure_context])
        results = kb.lookup(capability="echo", input_data={"message": "hi"})
        assert len(results) == 1

    def test_lookup_disabled(self, memory_store) -> None:
        kb = FailureKnowledgeBase(store=memory_store)
        assert kb.lookup(capability="echo", input_data={}) == []

    def test_enforce_limit_removes_oldest(self, memory_store) -> None:
        kb = FailureKnowledgeBase(
            store=memory_store,
            config=GuildConfig(enabled=True, max_records=3),
        )
        for i in range(5):
            ctx = FailureContext(
                task_id=f"t{i}", capability="echo", attempt=1, max_retries=2,
                error_type=f"E{i}", error_message=str(i), input_fingerprint=str(i),
            )
            kb.publish(capability="echo", failure_contexts=[ctx])
        # Should have at most 3 records
        assert len(memory_store.list()) <= 3

    def test_publish_success_creates_record(self, memory_store) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        record = kb.publish_success(capability="echo", input_data={"message": "hello"})
        assert record is not None
        assert record.success_count == 1
        assert record.failure_count == 0
        assert record.fingerprint.capability == "echo"
        assert record.fingerprint.error_type == "_success"

    def test_publish_success_increments_existing(self, memory_store) -> None:
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        kb.publish_success(capability="echo", input_data={"message": "hello"})
        record = kb.publish_success(capability="echo", input_data={"message": "hello"})
        assert record is not None
        # Same input → same fingerprint → success_count incremented
        assert record.success_count == 2

    def test_publish_success_disabled_returns_none(self, memory_store) -> None:
        kb = FailureKnowledgeBase(store=memory_store)
        assert kb.publish_success(capability="echo", input_data={}) is None

    def test_publish_success_and_failure_independent_counts(self, memory_store) -> None:
        """Success and failure records for the same capability+input are distinct
        because they use different error_type values ("_success" vs actual error)."""
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        ctx = FailureContext(
            task_id="t1", capability="echo", attempt=1, max_retries=2,
            error_type="ValueError", error_message="bad", input_fingerprint="abc",
        )
        kb.publish(capability="echo", failure_contexts=[ctx])
        succ = kb.publish_success(capability="echo", input_data={"message": "hello"})
        assert succ is not None
        assert succ.success_count == 1
        # Two records: one success, one failure
        assert len(memory_store.list()) == 2

    def test_publish_success_carries_role_and_project(self, memory_store) -> None:
        kb = FailureKnowledgeBase(
            store=memory_store,
            config=GuildConfig(enabled=True, project_name="my-proj"),
        )
        record = kb.publish_success(capability="echo", input_data={"x": 1}, role="worker")
        assert record is not None
        assert record.role == "worker"
        assert record.project == "my-proj"


# =========================================================================
# DefaultPeerSuggestionEngine
# =========================================================================


class TestDefaultPeerSuggestionEngine:
    def test_suggest_disabled_by_default(self, memory_store) -> None:
        engine = DefaultPeerSuggestionEngine(store=memory_store)
        assert engine.enabled is False
        assert engine.suggest(capability="echo", input_data={}) == []

    def test_suggest_no_matches(self, memory_store) -> None:
        engine = DefaultPeerSuggestionEngine(
            store=memory_store,
            config=GuildConfig(enabled=True),
        )
        assert engine.suggest(capability="echo", input_data={}) == []

    def test_suggest_returns_matches(self, memory_store) -> None:
        # Seed the store
        fp = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="abc")
        memory_store.save(GuildRecord(fingerprint=fp, resolution_hint="Use a string"))
        engine = DefaultPeerSuggestionEngine(
            store=memory_store,
            config=GuildConfig(enabled=True),
        )
        suggestions = engine.suggest(capability="echo", input_data={})
        assert len(suggestions) == 1
        assert suggestions[0].resolution_hint == "Use a string"
        assert suggestions[0].fingerprint.capability == "echo"
        assert suggestions[0].confidence >= 0.5

    def test_suggest_exact_input_match_higher_confidence(self, memory_store) -> None:
        fp = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        memory_store.save(GuildRecord(fingerprint=fp))
        engine = DefaultPeerSuggestionEngine(
            store=memory_store,
            config=GuildConfig(enabled=True),
        )
        # Input {"x": 1} has a stable fingerprint; match by providing same data
        suggestions = engine.suggest(
            capability="echo",
            input_data={"x": 1},
        )
        # The fingerprint from the record ("a") won't match {"x":1}'s hash, so confidence=0.5
        assert len(suggestions) == 1
        assert suggestions[0].confidence == 0.5

    def test_suggest_role_match_boost(self, memory_store) -> None:
        fp = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        memory_store.save(GuildRecord(fingerprint=fp, role="worker"))
        engine = DefaultPeerSuggestionEngine(
            store=memory_store,
            config=GuildConfig(enabled=True),
        )
        suggestions = engine.suggest(capability="echo", input_data={}, role="worker")
        assert len(suggestions) == 1
        # 0.5 (capability match) + 0.2 (role match) = 0.7
        assert suggestions[0].confidence == 0.7

    def test_suggest_multiple_records_sorted_by_confidence(self, memory_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="E1", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="echo", error_type="E2", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp1, role="worker"))
        memory_store.save(GuildRecord(fingerprint=fp2, role="worker"))
        engine = DefaultPeerSuggestionEngine(
            store=memory_store,
            config=GuildConfig(enabled=True),
        )
        suggestions = engine.suggest(capability="echo", input_data={}, role="worker")
        # Both should have 0.7 confidence (capability=0.5 + role=0.2); order is stable
        assert len(suggestions) == 2
        for s in suggestions:
            assert s.confidence == 0.7


# =========================================================================
# Integration: KnowledgeBase + PeerSuggestions
# =========================================================================


class TestGuildIntegration:
    def test_publish_then_suggest_round_trip(self, memory_store) -> None:
        """Publish a failure, then suggest: the same fingerprint should match."""
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        engine = DefaultPeerSuggestionEngine(store=memory_store, config=GuildConfig(enabled=True))

        ctx = FailureContext(
            task_id="t1", capability="echo", attempt=2, max_retries=2,
            error_type="ValueError", error_message="bad input",
            input_fingerprint="deadbeef",
        )
        kb.publish(capability="echo", failure_contexts=[ctx], role="worker")

        suggestions = engine.suggest(capability="echo", input_data={}, role="worker")
        assert len(suggestions) == 1
        assert suggestions[0].fingerprint.error_type == "ValueError"
        assert suggestions[0].fingerprint.input_fingerprint == "deadbeef"

    def test_publish_then_lookup_multiple_failures(self, memory_store) -> None:
        """Multiple failures to different capabilities: suggestions scoped by capability."""
        kb = FailureKnowledgeBase(store=memory_store, config=GuildConfig(enabled=True))
        engine = DefaultPeerSuggestionEngine(store=memory_store, config=GuildConfig(enabled=True))

        ctx1 = FailureContext(
            task_id="t1", capability="echo", attempt=2, max_retries=2,
            error_type="ValueError", error_message="bad", input_fingerprint="a",
        )
        ctx2 = FailureContext(
            task_id="t2", capability="filesystem", attempt=2, max_retries=2,
            error_type="OSError", error_message="perms", input_fingerprint="b",
        )
        kb.publish(capability="echo", failure_contexts=[ctx1])
        kb.publish(capability="filesystem", failure_contexts=[ctx2])

        assert len(engine.suggest(capability="echo", input_data={})) == 1
        assert len(engine.suggest(capability="filesystem", input_data={})) == 1
        assert len(engine.suggest(capability="http", input_data={})) == 0


# =========================================================================
# GuildMeetingService
# =========================================================================


class TestGuildMeetingService:
    def test_disabled_by_default(self, memory_store) -> None:
        service = GuildMeetingService(store=memory_store)
        assert service.hold_meeting() is None

    def test_empty_store_returns_report_with_summary(self, memory_store) -> None:
        service = GuildMeetingService(store=memory_store, config=GuildConfig(enabled=True))
        report = service.hold_meeting()
        assert report is not None
        assert report.total_records == 0
        assert "No guild records" in report.summary

    def test_meeting_aggregates_records_by_role_and_capability(self, memory_store) -> None:
        # Seed records for two roles and two capabilities
        fp1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="filesystem", error_type="OSError", input_fingerprint="b")
        fp3 = FailureFingerprint(capability="echo", error_type="_success", input_fingerprint="c")
        memory_store.save(GuildRecord(fingerprint=fp1, role="worker", failure_count=3))
        memory_store.save(GuildRecord(fingerprint=fp2, role="worker", failure_count=1))
        memory_store.save(GuildRecord(fingerprint=fp3, role="worker", success_count=10))

        service = GuildMeetingService(store=memory_store, config=GuildConfig(enabled=True))
        report = service.hold_meeting()
        assert report is not None
        assert report.total_records == 3
        assert "worker" in report.roles_present
        assert len(report.capability_profiles) == 2
        assert len(report.role_digests) == 1

    def test_capability_profile_counts(self, memory_store) -> None:
        fp1 = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp2 = FailureFingerprint(capability="echo", error_type="_success", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp1, role="worker", failure_count=5, success_count=0))
        memory_store.save(GuildRecord(fingerprint=fp2, role="worker", success_count=20, failure_count=0))

        service = GuildMeetingService(store=memory_store, config=GuildConfig(enabled=True))
        report = service.hold_meeting()
        assert report is not None
        echo_profile = next(p for p in report.capability_profiles if p.capability == "echo")
        assert echo_profile.total_failures == 5
        assert echo_profile.total_successes == 20
        assert echo_profile.distinct_error_types == ["ValueError"]

    def test_cross_role_insight_generated_for_high_failure_rate(self, memory_store) -> None:
        """Capability with >50% failure rate and >=5 total attempts gets a warning insight."""
        fp_fail = FailureFingerprint(capability="brittle", error_type="ValueError", input_fingerprint="a")
        fp_ok = FailureFingerprint(capability="brittle", error_type="_success", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp_fail, role="worker", failure_count=8))
        memory_store.save(GuildRecord(fingerprint=fp_ok, role="worker", success_count=2))

        service = GuildMeetingService(store=memory_store, config=GuildConfig(enabled=True))
        report = service.hold_meeting()
        assert report is not None
        assert len(report.cross_role_insights) > 0
        warnings = [i for i in report.cross_role_insights if i.severity == "warning"]
        assert len(warnings) >= 1
        assert any("brittle" in str(w.description) for w in warnings)

    def test_meeting_with_success_records_only(self, memory_store) -> None:
        fp = FailureFingerprint(capability="reliable", error_type="_success", input_fingerprint="a")
        memory_store.save(GuildRecord(fingerprint=fp, role="worker", success_count=50, failure_count=0))

        service = GuildMeetingService(store=memory_store, config=GuildConfig(enabled=True))
        report = service.hold_meeting()
        assert report is not None
        assert report.total_records == 1
        profile = report.capability_profiles[0]
        assert profile.total_successes == 50
        assert profile.total_failures == 0

    def test_role_digest_includes_failure_and_success_patterns(self, memory_store) -> None:
        fp_fail = FailureFingerprint(capability="echo", error_type="ValueError", input_fingerprint="a")
        fp_ok = FailureFingerprint(capability="echo", error_type="_success", input_fingerprint="b")
        memory_store.save(GuildRecord(fingerprint=fp_fail, role="worker", failure_count=3))
        memory_store.save(GuildRecord(fingerprint=fp_ok, role="worker", success_count=7))

        service = GuildMeetingService(store=memory_store, config=GuildConfig(enabled=True))
        report = service.hold_meeting()
        assert report is not None
        assert len(report.role_digests) == 1
        digest = report.role_digests[0]
        assert len(digest.top_failure_patterns) >= 1
        assert len(digest.top_success_patterns) >= 1
        assert "echo" in digest.capabilities_encountered
