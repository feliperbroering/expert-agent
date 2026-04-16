"""Unit tests for `CacheManager` against `mock-firestore`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.cache.manager import CacheManager
from app.docs.manifest import FileEntry, SyncManifest


def _manifest(gcs_uri: str = "gs://bucket/example-expert/abc/file.md") -> SyncManifest:
    entry = FileEntry(
        sha256="a" * 64,
        size=42,
        gcs_uri=gcs_uri,
        mime_type="text/markdown",
        updated_at=datetime.now(tz=UTC),
    )
    return SyncManifest(files={"file.md": entry})


@pytest.mark.asyncio
async def test_get_or_create_builds_fresh_cache_when_no_state(firestore_mock, fake_llm) -> None:
    manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="You are an expert.",
        ttl_seconds=3600,
    )
    manifest = _manifest()

    cache = await manager.get_or_create(manifest)

    assert cache.name == "cachedContents/0001"
    assert manager.current is cache
    stored = (
        firestore_mock.collection("agents")
        .document("example-expert")
        .collection("state")
        .document("cache")
        .get()
        .to_dict()
    )
    assert stored["cache_name"] == cache.name
    assert stored["sync_manifest_sha"] == manifest.sha256()
    assert len(fake_llm.created_caches) == 1


@pytest.mark.asyncio
async def test_get_or_create_reloads_non_expired_state(firestore_mock, fake_llm) -> None:
    ref = (
        firestore_mock.collection("agents")
        .document("example-expert")
        .collection("state")
        .document("cache")
    )
    expire_time = datetime.now(tz=UTC) + timedelta(hours=2)
    ref.set(
        {
            "cache_name": "cachedContents/preexisting",
            "expire_time": expire_time,
            "model": "gemini-test",
            "sync_manifest_sha": "deadbeef",
        }
    )

    manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="You are an expert.",
        ttl_seconds=3600,
    )
    cache = await manager.get_or_create(_manifest())

    assert cache.name == "cachedContents/preexisting"
    assert fake_llm.created_caches == []


@pytest.mark.asyncio
async def test_recreate_deletes_old_and_saves_new(firestore_mock, fake_llm) -> None:
    manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="sys",
        ttl_seconds=3600,
    )
    manifest1 = _manifest("gs://bucket/example-expert/aaa/a.md")
    await manager.get_or_create(manifest1)
    first_name = manager.current.name  # type: ignore[union-attr]

    manifest2 = _manifest("gs://bucket/example-expert/bbb/b.md")
    new_cache = await manager.recreate(manifest2)

    assert new_cache.name != first_name
    assert first_name in fake_llm.deleted_caches


@pytest.mark.asyncio
async def test_handle_cache_not_found_uses_loader(firestore_mock, fake_llm) -> None:
    manifest = _manifest()

    async def loader() -> SyncManifest:
        return manifest

    manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="sys",
        ttl_seconds=3600,
        manifest_loader=loader,
    )

    cache = await manager.handle_cache_not_found()
    assert cache.name.startswith("cachedContents/")
    assert len(fake_llm.created_caches) == 1
