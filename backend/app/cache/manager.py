"""Tracks the active Gemini Context Cache and persists it in Firestore.

State schema at `agents/{agent_id}/state/cache`::

    {
      "cache_name":       str,                 # e.g. "cachedContents/abc123"
      "expire_time":      datetime (UTC),
      "model":            str,
      "sync_manifest_sha": str,                # sha256 of the synced manifest
    }

Firestore writes happen in a thread pool so the client can stay sync (which
keeps the `mock-firestore` test double compatible).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import structlog

from ..docs.manifest import SyncManifest
from ..llm.protocol import CacheRef, FileRef, LLMClient

logger = structlog.get_logger(__name__)

ManifestLoader = Callable[[], Awaitable[SyncManifest | None]]


class CacheManager:
    """Owns the current `CacheRef` for this service instance."""

    def __init__(
        self,
        *,
        agent_id: str,
        llm: LLMClient,
        firestore_client: Any,
        system_instruction: str,
        ttl_seconds: int,
        manifest_loader: ManifestLoader | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._llm = llm
        self._firestore = firestore_client
        self._system_instruction = system_instruction
        self._ttl_seconds = ttl_seconds
        self._manifest_loader = manifest_loader
        self._current: CacheRef | None = None
        self._lock = asyncio.Lock()

    @property
    def current(self) -> CacheRef | None:
        return self._current

    def _state_ref(self) -> Any:
        return (
            self._firestore.collection("agents")
            .document(self._agent_id)
            .collection("state")
            .document("cache")
        )

    async def _load_state(self) -> dict[str, Any] | None:
        def _read() -> dict[str, Any] | None:
            snap = self._state_ref().get()
            if not getattr(snap, "exists", False):
                return None
            data = snap.to_dict() or {}
            return dict(data)

        return await asyncio.to_thread(_read)

    async def _save_state(self, cache: CacheRef, manifest_sha: str | None) -> None:
        payload: dict[str, Any] = {
            "cache_name": cache.name,
            "expire_time": cache.expire_time,
            "model": cache.model,
            "sync_manifest_sha": manifest_sha or "",
            "updated_at": datetime.now(tz=UTC),
        }

        def _write() -> None:
            self._state_ref().set(payload, merge=True)

        await asyncio.to_thread(_write)

    async def _clear_state(self) -> None:
        def _delete() -> None:
            self._state_ref().delete()

        await asyncio.to_thread(_delete)

    async def get_or_create(self, manifest: SyncManifest | None = None) -> CacheRef:
        """Return the live cache, loading from Firestore or creating a fresh one."""
        async with self._lock:
            if self._current is not None and not _is_expired(self._current):
                return self._current

            stored = await self._load_state()
            if stored:
                expire = _coerce_datetime(stored.get("expire_time"))
                candidate = CacheRef(
                    name=str(stored["cache_name"]),
                    expire_time=expire,
                    model=str(stored.get("model", "")),
                )
                if not _is_expired(candidate):
                    self._current = candidate
                    logger.info(
                        "cache.loaded",
                        cache_name=candidate.name,
                        expires_in_s=_seconds_until(candidate.expire_time),
                    )
                    return candidate

            if manifest is None and self._manifest_loader is not None:
                manifest = await self._manifest_loader()
            if manifest is None:
                raise RuntimeError(
                    "CacheManager.get_or_create: no manifest available to build cache"
                )

            return await self._recreate_locked(manifest)

    async def recreate(self, manifest: SyncManifest) -> CacheRef:
        """Delete any existing cache and create a new one from `manifest`."""
        async with self._lock:
            return await self._recreate_locked(manifest)

    async def _recreate_locked(self, manifest: SyncManifest) -> CacheRef:
        old = self._current
        docs = _manifest_to_filerefs(manifest)
        new = await self._llm.create_cache(
            docs=docs,
            system_instruction=self._system_instruction,
            ttl_seconds=self._ttl_seconds,
        )
        # Persist the model we actually used even if the SDK response was empty.
        if not new.model:
            new = replace(new, model=getattr(self._llm, "model", ""))
        await self._save_state(new, manifest.sha256())
        self._current = new
        logger.info(
            "cache.recreated",
            cache_name=new.name,
            file_count=len(docs),
            manifest_sha=manifest.sha256(),
        )
        if old is not None and old.name != new.name:
            try:
                await self._llm.delete_cache(old)
            except Exception as exc:  # pragma: no cover - best-effort
                logger.warning("cache.old_delete_failed", cache_name=old.name, error=str(exc))
        return new

    async def handle_cache_not_found(self) -> CacheRef:
        """Recreate the cache after the LLM reported it as missing/expired."""
        if self._manifest_loader is None:
            raise RuntimeError("CacheManager.handle_cache_not_found: no manifest loader configured")
        manifest = await self._manifest_loader()
        if manifest is None:
            raise RuntimeError("No sync manifest available for cache recreation")
        async with self._lock:
            self._current = None
            await self._clear_state()
            return await self._recreate_locked(manifest)


def _manifest_to_filerefs(manifest: SyncManifest) -> list[FileRef]:
    return [
        FileRef(gcs_uri=entry.gcs_uri, mime_type=entry.mime_type)
        for entry in manifest.files.values()
    ]


def _is_expired(cache: CacheRef) -> bool:
    return _seconds_until(cache.expire_time) <= 0


def _seconds_until(when: datetime) -> float:
    now = datetime.now(tz=UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (when - now).total_seconds()


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(tz=UTC)


__all__ = ["CacheManager", "ManifestLoader"]
