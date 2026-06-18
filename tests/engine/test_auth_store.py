"""Tests for the API key store."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from engine.api.auth import ApiKeyStore


def test_empty_store_no_auth() -> None:
    store = ApiKeyStore.empty()
    assert not store.enabled
    assert not store.has_keys
    assert store.list_keys() == []


def test_empty_store_from_nonexistent_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "noexist.json"
        store = ApiKeyStore(path)
        assert not store.enabled
        assert store.list_keys() == []


def test_generate_returns_key_and_entry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)

        assert not store.enabled

        raw, entry = store.generate(actor="test-bot", scopes=["task:read"])
        assert raw.startswith("cond_")
        assert len(raw) > 12
        assert entry.actor == "test-bot"
        assert entry.scopes == ["task:read"]
        assert entry.prefix == raw[:12]

        assert store.enabled
        assert store.has_keys


def test_lookup_valid_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)

        raw, _ = store.generate(actor="bot")
        entry = store.lookup(raw)
        assert entry is not None
        assert entry.actor == "bot"
        assert entry.last_used_at is not None


def test_lookup_bogus_key_returns_none() -> None:
    store = ApiKeyStore(tempfile.mktemp(suffix=".json"))
    store.generate(actor="bot")
    assert store.lookup("cond_boguskey1234567890abcdef1234567890abcdef") is None


def test_lookup_revoked_key_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)
        raw, entry = store.generate(actor="bot")

        store.revoke(entry.key_hash)
        assert store.lookup(raw) is None


def test_revoke_by_hash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)
        _, entry = store.generate(actor="bot")

        assert store.revoke(entry.key_hash) is True
        assert store.revoke("nonexistent") is False
        entries = store.list_keys()
        assert entries[0].revoked is True


def test_find_by_prefix() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)
        raw, entry = store.generate(actor="bot")

        found = store.find_by_prefix(raw[:12])
        assert found is not None
        assert found.actor == "bot"

        assert store.find_by_prefix("cond_nonexistent") is None


def test_persistence_across_reload() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"

        # Create a key
        store1 = ApiKeyStore(path)
        raw, entry = store1.generate(actor="persist-bot", scopes=["task:write"])

        # Reload from same file
        store2 = ApiKeyStore(path)
        assert store2.enabled
        assert len(store2.list_keys()) == 1
        assert store2.lookup(raw) is not None

        loaded = store2.list_keys()[0]
        assert loaded.actor == "persist-bot"
        assert loaded.scopes == ["task:write"]
        assert loaded.key_hash == entry.key_hash


def test_revocation_persists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"

        store1 = ApiKeyStore(path)
        raw, entry = store1.generate(actor="bot")
        store1.revoke(entry.key_hash)

        store2 = ApiKeyStore(path)
        assert store2.lookup(raw) is None
        assert store2.list_keys()[0].revoked is True


def test_enabled_only_when_keys_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)
        assert not store.enabled

        store.generate(actor="bot")
        assert store.enabled

        # Revoking all keys disables auth
        for e in store.list_keys():
            store.revoke(e.key_hash)
        assert not store.enabled


def test_default_scopes_wildcard() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = ApiKeyStore(Path(tmp) / "keys.json")
        _, entry = store.generate(actor="bot")
        assert entry.scopes == ["*"]


def test_json_file_is_written() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = ApiKeyStore(path)
        store.generate(actor="bot")

        raw = path.read_text()
        data = json.loads(raw)
        assert len(data) == 1
        key_hash = next(iter(data.keys()))
        assert data[key_hash]["actor"] == "bot"


def test_load_api_key_store_importable() -> None:
    from engine.api.auth import load_api_key_store

    empty = load_api_key_store(None)
    assert isinstance(empty, ApiKeyStore)
    assert not empty.enabled
