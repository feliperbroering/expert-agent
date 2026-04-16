"""Tests for the `/docs/sync` pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.cache.manager import CacheManager
from app.docs.manifest import (
    FileEntry,
    SyncManifest,
    compute_file_sha256,
    diff_manifests,
    manifest_from_directory,
)
from app.docs.sync import (
    MANIFEST_OBJECT_SUFFIX,
    DocsSyncRequest,
    DocsSyncService,
    InMemoryGcsClient,
    SyncLockError,
)


def _entry(sha: str, uri: str) -> FileEntry:
    return FileEntry(
        sha256=sha,
        size=10,
        gcs_uri=uri,
        mime_type="text/markdown",
        updated_at=datetime.now(tz=UTC),
    )


def test_diff_manifests_identifies_added_removed_changed() -> None:
    old = SyncManifest(
        files={
            "keep.md": _entry("a" * 64, "gs://b/keep"),
            "change.md": _entry("b" * 64, "gs://b/change-old"),
            "gone.md": _entry("c" * 64, "gs://b/gone"),
        }
    )
    new = SyncManifest(
        files={
            "keep.md": _entry("a" * 64, "gs://b/keep"),
            "change.md": _entry("d" * 64, "gs://b/change-new"),
            "added.md": _entry("e" * 64, "gs://b/added"),
        }
    )
    diff = diff_manifests(old, new)

    assert diff.added == ["added.md"]
    assert diff.removed == ["gone.md"]
    assert diff.changed == ["change.md"]
    assert diff.has_changes is True


def test_manifest_from_directory(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello", encoding="utf-8")
    (tmp_path / "b.md").write_text("world", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.md").write_text("deep", encoding="utf-8")
    (tmp_path / "_drafts").mkdir()
    (tmp_path / "_drafts" / "ignore.md").write_text("drafts", encoding="utf-8")

    manifest = manifest_from_directory(
        tmp_path,
        include=["*.md"],
        exclude=["_drafts/*"],
        gcs_uri_for=lambda rel, entry: f"gs://bucket/{entry.sha256[:8]}/{rel}",
    )

    keys = sorted(manifest.files)
    assert keys == ["a.md", "b.md", "nested/c.md"]
    for entry in manifest.files.values():
        assert entry.gcs_uri.startswith("gs://bucket/")
        assert len(entry.sha256) == 64


def test_compute_file_sha256(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"hello")
    # sha256("hello") = 2cf24db...
    assert compute_file_sha256(path).startswith("2cf24dba")


@pytest.mark.asyncio
async def test_sync_adds_new_files_and_recreates_cache(
    tmp_path: Path, firestore_mock, fake_llm
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# one", encoding="utf-8")
    (docs_dir / "two.md").write_text("# two", encoding="utf-8")

    gcs = InMemoryGcsClient()
    cache_manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="sys",
        ttl_seconds=3600,
    )

    service = DocsSyncService(
        agent_id="example-expert",
        docs_bucket="my-bucket",
        firestore_client=firestore_mock,
        gcs_client=gcs,
        cache_manager=cache_manager,
        docs_dir=docs_dir,
        include_patterns=["*.md"],
    )

    result = await service.sync(DocsSyncRequest())

    assert sorted(result.diff.added) == ["one.md", "two.md"]
    assert result.cache_recreated is True
    assert len(fake_llm.created_caches) == 1
    # Manifest persisted to GCS under the expected key.
    manifest_key = f"example-expert/{MANIFEST_OBJECT_SUFFIX}"
    assert gcs.sync_manifest_payload("my-bucket", "example-expert") is not None
    # Object keys follow the {agent_id}/{sha[:8]}/{filename} layout.
    keys = [k for (b, k) in gcs.dump() if b == "my-bucket" and k != manifest_key]
    assert any(k.startswith("example-expert/") and k.endswith("/one.md") for k in keys)


@pytest.mark.asyncio
async def test_sync_is_noop_when_manifest_matches(tmp_path: Path, firestore_mock, fake_llm) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# one", encoding="utf-8")

    gcs = InMemoryGcsClient()
    cache_manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="sys",
        ttl_seconds=3600,
    )
    service = DocsSyncService(
        agent_id="example-expert",
        docs_bucket="my-bucket",
        firestore_client=firestore_mock,
        gcs_client=gcs,
        cache_manager=cache_manager,
        docs_dir=docs_dir,
        include_patterns=["*.md"],
    )

    first = await service.sync(DocsSyncRequest())
    assert first.cache_recreated is True

    second = await service.sync(DocsSyncRequest())
    assert second.cache_recreated is False
    assert second.diff.has_changes is False


@pytest.mark.asyncio
async def test_sync_lock_blocks_concurrent_callers(
    tmp_path: Path, firestore_mock, fake_llm
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("x", encoding="utf-8")

    gcs = InMemoryGcsClient()
    cache_manager = CacheManager(
        agent_id="example-expert",
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="sys",
        ttl_seconds=3600,
    )
    service = DocsSyncService(
        agent_id="example-expert",
        docs_bucket="my-bucket",
        firestore_client=firestore_mock,
        gcs_client=gcs,
        cache_manager=cache_manager,
        docs_dir=docs_dir,
        include_patterns=["*.md"],
    )

    # Simulate a held lock by writing a non-expired entry directly.
    from datetime import timedelta

    (
        firestore_mock.collection("agents")
        .document("example-expert")
        .collection("state")
        .document("sync_lock")
        .set(
            {
                "holder": "someone-else",
                "expires_at": datetime.now(tz=UTC) + timedelta(minutes=10),
            }
        )
    )

    with pytest.raises(SyncLockError):
        await service.sync(DocsSyncRequest())
