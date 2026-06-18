"""File-backed API key store.

Keys are stored as SHA-256 hashes — the raw key is shown exactly once,
at creation time.  The store is a simple JSON file::

    {
      "<key_hash>": {
        "prefix": "cond_abc",
        "actor": "deploy-bot",
        "scopes": ["task:write", "task:read"],
        "created_at": "2026-06-17T12:00:00",
        "last_used_at": null,
        "revoked": false
      }
    }
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import secrets
from typing import Any

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


class ApiKeyEntry:
    """Describes a single API key (without the raw secret)."""

    def __init__(
        self,
        *,
        key_hash: str,
        prefix: str,
        actor: str = "api",
        scopes: list[str] | None = None,
        created_at: str | None = None,
        last_used_at: str | None = None,
        revoked: bool = False,
    ) -> None:
        self.key_hash = key_hash
        self.prefix = prefix
        self.actor = actor
        self.scopes = scopes or ["*"]
        self.created_at = created_at or _now_iso()
        self.last_used_at = last_used_at
        self.revoked = revoked

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "actor": self.actor,
            "scopes": self.scopes,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "revoked": self.revoked,
        }

    @classmethod
    def from_dict(cls, key_hash: str, data: dict[str, Any]) -> ApiKeyEntry:
        return cls(
            key_hash=key_hash,
            prefix=data["prefix"],
            actor=data.get("actor", "api"),
            scopes=data.get("scopes", ["*"]),
            created_at=data.get("created_at"),
            last_used_at=data.get("last_used_at"),
            revoked=data.get("revoked", False),
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

KEY_PREFIX = "cond_"
_KEY_BYTES = 32  # 256-bit random


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_raw_key() -> str:
    """Return a human-readable API key like ``cond_a1b2c3d4e5...``."""
    raw = secrets.token_hex(_KEY_BYTES)
    return f"{KEY_PREFIX}{raw}"


class ApiKeyStore:
    """File-backed store for hashed API keys.

    The store is a simple JSON file.  If the file does not exist the
    store is empty — the API runs in open (no-auth) mode.  Once at
    least one key exists, authentication is enforced.

    Thread-safety is best-effort via atomic write (write to temp,
    rename).  Not suitable for concurrent CLI/server access to the
    same file.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._entries: dict[str, ApiKeyEntry] = {}
        self._dirty = False
        self._load()

    @classmethod
    def empty(cls) -> ApiKeyStore:
        """Return a store with no keys and no backing file (auth disabled)."""
        store = cls.__new__(cls)
        store._path = None  # type: ignore[assignment]
        store._entries = {}
        store._dirty = False
        return store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def has_keys(self) -> bool:
        """True when at least one non-revoked key exists."""
        return any(not e.revoked for e in self._entries.values())

    @property
    def enabled(self) -> bool:
        """Authentication is enforced when keys exist."""
        return self.has_keys

    def generate(self, *, actor: str = "api", scopes: list[str] | None = None) -> tuple[str, ApiKeyEntry]:
        """Create a new key and return ``(raw_key, entry)``.

        The raw key is returned exactly once — it cannot be recovered
        from the store after this call.
        """
        raw = generate_raw_key()
        key_hash = _hash_key(raw)
        prefix = raw[:12]  # e.g. "cond_a1b2c3d4"
        entry = ApiKeyEntry(
            key_hash=key_hash,
            prefix=prefix,
            actor=actor,
            scopes=scopes,
        )
        self._entries[key_hash] = entry
        self._dirty = True
        self._save()
        return raw, entry

    def lookup(self, raw_key: str) -> ApiKeyEntry | None:
        """Look up a raw key.  Returns ``None`` if unknown or revoked.

        Checks the backing file for external changes on every call
        (lightweight ``mtime`` check) so that ``cond api-key revoke``
        from another process is reflected without a server restart.
        """
        self._reload_if_changed()
        key_hash = _hash_key(raw_key)
        entry = self._entries.get(key_hash)
        if entry is None or entry.revoked:
            return None
        # Update last_used_at in-memory (don't write on every lookup in hot path)
        entry.last_used_at = _now_iso()
        return entry

    def flush_usage(self) -> None:
        """Persist usage timestamps to disk."""
        if self._dirty:
            self._save()
            self._dirty = False

    def revoke(self, key_hash: str) -> bool:
        """Revoke a key by its hash.  Returns False if not found."""
        entry = self._entries.get(key_hash)
        if entry is None:
            return False
        entry.revoked = True
        self._dirty = True
        self._save()
        return True

    def _reload_if_changed(self) -> None:
        """Reload from the backing file if its mtime has changed.

        This ensures external key management (``cond api-key revoke``
        from another process) is reflected without a server restart.
        """
        if self._path is None or not self._path.exists():
            return
        try:
            current_mtime = self._path.stat().st_mtime
        except OSError:
            return
        if not hasattr(self, "_last_mtime"):
            self._last_mtime: float = 0.0
        if current_mtime > self._last_mtime:
            self._load()
            self._last_mtime = current_mtime

    def list_keys(self) -> list[ApiKeyEntry]:
        """Return all entries (including revoked)."""
        return list(self._entries.values())

    def find_by_prefix(self, prefix: str) -> ApiKeyEntry | None:
        """Find a single entry by key prefix (for CLI display)."""
        for entry in self._entries.values():
            if entry.prefix == prefix:
                return entry
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        try:
            raw = self._path.read_text()
            data: dict[str, Any] = json.loads(raw)
            self._entries = {
                kh: ApiKeyEntry.from_dict(kh, d) for kh, d in data.items()
            }
        except (json.JSONDecodeError, KeyError):
            self._entries = {}

    def _save(self) -> None:
        if self._path is None:
            return  # empty store, no backing file
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {kh: e.to_dict() for kh, e in self._entries.items()}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self._path)


def load_api_key_store(path: str | Path | None) -> ApiKeyStore:
    """Load or create an ``ApiKeyStore`` from *path*.

    Returns an empty store when *path* is ``None`` (auth is disabled).
    """
    if path is None:
        return ApiKeyStore.empty()
    return ApiKeyStore(path)
