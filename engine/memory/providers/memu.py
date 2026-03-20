"""memU-backed implementation of the engine memory provider contract."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from engine.interfaces.memory import MemoryDocument, MemoryHit, MemoryQuery


def _load_memu_service() -> type[Any]:
    try:
        module = import_module("memu")
    except ImportError as exc:
        raise RuntimeError(
            "memU Python SDK is not installed. Install the self-hosted memU package to enable "
            "memory support."
        ) from exc

    try:
        return module.MemUService
    except AttributeError as exc:
        raise RuntimeError("memU Python SDK does not export MemUService") from exc


class MemUProvider:
    """Adapter around memU's async MemUService API."""

    def __init__(
        self,
        *,
        service: Any | None = None,
        service_config: dict[str, Any] | None = None,
        scope: dict[str, Any] | None = None,
    ) -> None:
        self._service = service
        self._service_config = service_config or {}
        self._scope = scope or {}

    def _get_service(self) -> Any:
        if self._service is None:
            service_class = _load_memu_service()
            self._service = service_class(**self._service_config)
        return self._service

    async def memorize(self, documents: list[MemoryDocument]) -> list[dict[str, Any]]:
        service = self._get_service()
        results: list[dict[str, Any]] = []

        for document in documents:
            source_path = document.metadata.get("source_path")
            modality = str(document.metadata.get("modality", "document"))
            user_scope = {**self._scope, "namespace": document.namespace}

            if isinstance(document.metadata.get("scope"), dict):
                user_scope.update(document.metadata["scope"])

            cleanup_path: Path | None = None
            resource_url = str(source_path) if source_path else ""

            if not resource_url:
                with NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
                    tmp.write(document.content)
                    cleanup_path = Path(tmp.name)
                    resource_url = tmp.name

            try:
                raw = await service.memorize(
                    resource_url=resource_url,
                    modality=modality,
                    user=user_scope or None,
                )
            finally:
                if cleanup_path is not None and cleanup_path.exists():
                    cleanup_path.unlink()

            results.append(
                {
                    "external_id": document.external_id,
                    "namespace": document.namespace,
                    "raw": raw,
                }
            )

        return results

    async def retrieve(self, query: MemoryQuery) -> list[MemoryHit]:
        service = self._get_service()
        where = {**self._scope, **query.metadata_filters}
        if query.namespaces:
            where["namespace__in"] = query.namespaces

        raw = await service.retrieve(
            queries=[{"role": "user", "content": {"text": query.query}}],
            where=where or None,
        )

        hits = self._normalize_hits(raw)
        if query.namespaces:
            hits = [
                hit
                for hit in hits
                if hit.metadata.get("namespace") in query.namespaces
                or hit.metadata.get("user", {}).get("namespace") in query.namespaces
            ]
        return hits[: query.limit]

    def _normalize_hits(self, raw: dict[str, Any]) -> list[MemoryHit]:
        hits: list[MemoryHit] = []

        for bucket_name in ("items", "categories", "resources"):
            entries = raw.get(bucket_name, [])
            if not isinstance(entries, list):
                continue

            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue

                metadata = self._extract_metadata(entry)
                hits.append(
                    MemoryHit(
                        external_id=self._extract_external_id(entry, bucket_name, index),
                        content=self._extract_content(entry),
                        metadata=metadata,
                        score=self._extract_score(entry),
                    )
                )

        return hits

    @staticmethod
    def _extract_external_id(entry: dict[str, Any], bucket_name: str, index: int) -> str:
        for key in ("external_id", "id", "item_id", "category_id", "resource_id"):
            value = entry.get(key)
            if value:
                return str(value)
        return f"{bucket_name}:{index}"

    @staticmethod
    def _extract_content(entry: dict[str, Any]) -> str:
        for key in ("content", "text", "summary", "description", "title"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(entry, sort_keys=True)

    @staticmethod
    def _extract_score(entry: dict[str, Any]) -> float | None:
        for key in ("score", "similarity"):
            value = entry.get(key)
            if isinstance(value, int | float):
                return float(value)
        return None

    @staticmethod
    def _extract_metadata(entry: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in ("metadata", "user", "scope", "resource"):
            value = entry.get(key)
            if isinstance(value, dict):
                if key == "metadata":
                    metadata.update(value)
                else:
                    metadata[key] = value

        if "namespace" in entry and "namespace" not in metadata:
            metadata["namespace"] = entry["namespace"]

        user = metadata.get("user")
        if isinstance(user, dict) and "namespace" in user and "namespace" not in metadata:
            metadata["namespace"] = user["namespace"]

        return metadata
