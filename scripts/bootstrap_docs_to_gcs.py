"""One-shot bootstrap: upload an agent's local docs to GCS and persist the manifest.

Use it the very first time you stand up an agent (or any time you want to bypass
`/docs/sync` and rebuild the manifest by hand). After this runs, the next call to
`/ask` triggers `CacheManager.get_or_create` → `manifest_loader` (reads
`gs://{docs_bucket}/{agent_id}/_state/sync_manifest.json` from GCS) → creates the
Context Cache.

Usage:

    uv run python scripts/bootstrap_docs_to_gcs.py \
        --agent-id <AGENT_ID> \
        --schema /path/to/<AGENT_ID>/agent_schema.yaml \
        --bucket <PROJECT_ID>-docs \
        --project <PROJECT_ID>
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.docs.manifest import (
    FileEntry,
    SyncManifest,
    compute_file_sha256,
    guess_mime,
    manifest_from_directory,
)
from app.schema import AgentSchema
from google.cloud import storage  # type: ignore[attr-defined]

# Mirror `app.docs.sync.MANIFEST_OBJECT_SUFFIX` here without importing it,
# because importing `app.docs.sync` would pull in structlog/slowapi/fastapi
# (heavy runtime deps) when this script only needs google-cloud-storage +
# pydantic.
MANIFEST_OBJECT_SUFFIX = "_state/sync_manifest.json"


def _object_key(agent_id: str, relpath: str, sha256: str) -> str:
    """Mirrors `DocsSyncService._object_key` so the runtime sees the same paths."""
    basename = Path(relpath).name
    return f"{agent_id}/{sha256[:8]}/{basename}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()

    schema = AgentSchema.from_yaml(args.schema)
    base_dir = args.schema.parent
    docs_dir = (base_dir / schema.spec.knowledge.reference_docs_dir).resolve()
    if not docs_dir.exists():
        raise SystemExit(f"docs dir not found: {docs_dir}")

    print(f"[bootstrap] scanning {docs_dir}")
    walk_manifest = manifest_from_directory(
        docs_dir,
        include=schema.spec.knowledge.include_patterns,
        exclude=schema.spec.knowledge.exclude_patterns,
    )

    client = storage.Client(project=args.project)
    bucket = client.bucket(args.bucket)

    files: dict[str, FileEntry] = {}
    for relpath, _walked in walk_manifest.files.items():
        local = docs_dir / relpath
        sha = compute_file_sha256(local)
        mime = guess_mime(local)
        key = _object_key(args.agent_id, relpath, sha)
        gcs_uri = f"gs://{args.bucket}/{key}"

        blob = bucket.blob(key)
        if blob.exists():
            print(f"[bootstrap] skip (exists)  {gcs_uri}")
        else:
            print(f"[bootstrap] upload         {gcs_uri}")
            blob.upload_from_filename(str(local), content_type=mime)

        files[relpath] = FileEntry(
            sha256=sha,
            size=local.stat().st_size,
            gcs_uri=gcs_uri,
            mime_type=mime,
            updated_at=datetime.fromtimestamp(local.stat().st_mtime, tz=UTC),
        )

    manifest = SyncManifest(files=files)
    manifest_key = f"{args.agent_id}/{MANIFEST_OBJECT_SUFFIX}"
    bucket.blob(manifest_key).upload_from_string(
        manifest.model_dump_json(indent=2),
        content_type="application/json",
    )
    print(
        f"[bootstrap] manifest uploaded → gs://{args.bucket}/{manifest_key} "
        f"({len(manifest.files)} files, sha={manifest.sha256()[:12]}…)"
    )


if __name__ == "__main__":
    main()
