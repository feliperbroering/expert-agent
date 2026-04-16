"""SHA-256 manifest of the docs synced to GCS.

The manifest is the source of truth for which files the Context Cache was
built from. `/docs/sync` compares the incoming manifest with the stored one
to compute an incremental diff, then rebuilds the cache if anything changed.
"""

from __future__ import annotations

import fnmatch
import hashlib
import mimetypes
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MIME = "application/octet-stream"
_MIME_BY_SUFFIX = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
}

_SHA256_READ_CHUNK = 1024 * 1024


def compute_file_sha256(path: Path) -> str:
    """Stream a file into sha256 without loading it fully in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_SHA256_READ_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def guess_mime(path: Path) -> str:
    """Resolve a MIME type from the extension with sensible defaults."""
    suffix = path.suffix.lower()
    if suffix in _MIME_BY_SUFFIX:
        return _MIME_BY_SUFFIX[suffix]
    guessed, _ = mimetypes.guess_type(path.as_posix())
    return guessed or DEFAULT_MIME


class FileEntry(BaseModel):
    """Metadata for a single synced file."""

    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(min_length=64, max_length=64)
    size: int = Field(ge=0)
    gcs_uri: str
    mime_type: str
    updated_at: datetime


class SyncManifest(BaseModel):
    """Canonical form of the manifest persisted at `_state/sync_manifest.json`."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    files: dict[str, FileEntry] = Field(default_factory=dict)

    def sha256(self) -> str:
        """Stable aggregate hash used to detect full-manifest equivalence."""
        digest = hashlib.sha256()
        for name in sorted(self.files):
            digest.update(name.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(self.files[name].sha256.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()


class ManifestDiff(BaseModel):
    """Added/removed/changed file lists produced by `diff_manifests`."""

    model_config = ConfigDict(extra="forbid")

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def _matches_any(patterns: list[str], relpath: str) -> bool:
    return any(
        fnmatch.fnmatch(relpath, p) or fnmatch.fnmatch(Path(relpath).name, p) for p in patterns
    )


GcsUriFactory = Callable[[str, "FileEntry"], str]


def _default_gcs_uri(_relpath: str, _entry: FileEntry) -> str:
    return ""


def manifest_from_directory(
    root: Path,
    *,
    include: list[str],
    exclude: list[str] | None = None,
    gcs_uri_for: GcsUriFactory = _default_gcs_uri,
) -> SyncManifest:
    """Walk `root` and build a manifest from matching files.

    `gcs_uri_for(relpath, FileEntry)` is called after sha computation so the
    caller (DocsSyncService) can format URIs like
    `gs://bucket/{agent_id}/{sha256[:8]}/{filename}`.
    """
    exclude = exclude or []
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"reference_docs_dir not found: {root}")

    files: dict[str, FileEntry] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relpath = path.relative_to(root).as_posix()
        if not _matches_any(include, relpath):
            continue
        if exclude and _matches_any(exclude, relpath):
            continue

        sha = compute_file_sha256(path)
        stat = path.stat()
        entry = FileEntry(
            sha256=sha,
            size=stat.st_size,
            gcs_uri="",
            mime_type=guess_mime(path),
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )
        gcs_uri = gcs_uri_for(relpath, entry)
        files[relpath] = entry.model_copy(update={"gcs_uri": gcs_uri})

    return SyncManifest(files=files)


def diff_manifests(old: SyncManifest, new: SyncManifest) -> ManifestDiff:
    """Compute added/removed/changed relative paths between two manifests."""
    old_paths = set(old.files)
    new_paths = set(new.files)

    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    changed = sorted(
        p for p in (old_paths & new_paths) if old.files[p].sha256 != new.files[p].sha256
    )
    return ManifestDiff(added=added, removed=removed, changed=changed)


__all__ = [
    "DEFAULT_MIME",
    "FileEntry",
    "GcsUriFactory",
    "ManifestDiff",
    "SyncManifest",
    "compute_file_sha256",
    "diff_manifests",
    "guess_mime",
    "manifest_from_directory",
]
