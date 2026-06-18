"""Guild store implementations for failure knowledge persistence.

Provides:
    - MemoryGuildStore: in-memory dict-based store (testing / embedded)
    - LocalGuildStore: JSON-file-backed store suitable for single-node deployments
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from engine.guild.interface import FailureFingerprint, GuildRecord


class GuildRecordNotFoundError(KeyError):
    """Raised when a guild record lookup fails."""

    def __init__(self, fingerprint: FailureFingerprint) -> None:
        key = fingerprint.to_key()
        super().__init__(f"Guild record not found: {key}")
        self.fingerprint = fingerprint


def _compute_input_fingerprint(input_data: dict[str, Any]) -> str:
    """Compute a stable 16-character fingerprint of input shape."""
    return hashlib.sha256(
        json.dumps(input_data, sort_keys=True).encode()
    ).hexdigest()[:16]


def _filter_records(
    records: list[GuildRecord],
    *,
    capability: str | None = None,
    error_type: str | None = None,
    role: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[GuildRecord]:
    """Filter and paginate a list of guild records."""
    if capability is not None:
        records = [r for r in records if r.fingerprint.capability == capability]
    if error_type is not None:
        records = [r for r in records if r.fingerprint.error_type == error_type]
    if role is not None:
        records = [r for r in records if r.role == role]
    records = records[offset:]
    if limit is not None:
        records = records[:limit]
    return records


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------


class MemoryGuildStore:
    """In-memory guild store. Records are lost on restart.

    Suitable for tests and embedded runs where persistence is not required.
    All reads return deep copies.
    """

    def __init__(self) -> None:
        self._records: dict[str, GuildRecord] = {}

    def save(self, record: GuildRecord) -> GuildRecord:
        key = record.fingerprint.to_key()
        self._records[key] = record.model_copy(deep=True)
        return record

    def get(self, fingerprint: FailureFingerprint) -> GuildRecord | None:
        record = self._records.get(fingerprint.to_key())
        return record.model_copy(deep=True) if record is not None else None

    def list(
        self,
        *,
        capability: str | None = None,
        error_type: str | None = None,
        role: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GuildRecord]:
        records = [r.model_copy(deep=True) for r in self._records.values()]
        return _filter_records(
            records,
            capability=capability,
            error_type=error_type,
            role=role,
            limit=limit,
            offset=offset,
        )

    def delete(self, fingerprint: FailureFingerprint) -> bool:
        key = fingerprint.to_key()
        if key in self._records:
            del self._records[key]
            return True
        return False

    def clear(self) -> None:
        self._records.clear()


# ---------------------------------------------------------------------------
# JSON-file-backed store
# ---------------------------------------------------------------------------


class LocalGuildStore:
    """JSON-file-backed guild store for local deployments.

    Persists guild records to a JSON file, with atomic writes via
    temporary file + rename. Suitable for single-node deployments
    where durability across restarts is required.
    """

    def __init__(self, path: str | Path = ".conductor/guild.json") -> None:
        self.path = Path(path)

    def _read_all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _write_all(self, payload: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        tmp_path = Path(tmp_name)
        try:
            with open(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
            tmp_path.replace(self.path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def save(self, record: GuildRecord) -> GuildRecord:
        payload = self._read_all()
        key = record.fingerprint.to_key()
        payload[key] = record.model_dump(mode="json")
        self._write_all(payload)
        return record

    def get(self, fingerprint: FailureFingerprint) -> GuildRecord | None:
        payload = self._read_all()
        raw = payload.get(fingerprint.to_key())
        if raw is None:
            return None
        return GuildRecord.model_validate(raw)

    def list(
        self,
        *,
        capability: str | None = None,
        error_type: str | None = None,
        role: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GuildRecord]:
        payload = self._read_all()
        records = [GuildRecord.model_validate(r) for r in payload.values()]
        return _filter_records(
            records,
            capability=capability,
            error_type=error_type,
            role=role,
            limit=limit,
            offset=offset,
        )

    def delete(self, fingerprint: FailureFingerprint) -> bool:
        payload = self._read_all()
        key = fingerprint.to_key()
        if key in payload:
            del payload[key]
            self._write_all(payload)
            return True
        return False

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
