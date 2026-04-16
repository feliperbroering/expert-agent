"""Admin-only `/docs/sync` endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..auth import AdminUser
from ..deps import DocsSyncDep
from ..docs.sync import DocsSyncRequest, DocsSyncResponse, DocsSyncService, SyncLockError

router = APIRouter(prefix="/docs", tags=["docs"])


@router.post("/sync", response_model=DocsSyncResponse)
async def sync_docs(
    payload: DocsSyncRequest,
    docs_sync: DocsSyncDep,
    _: AdminUser,
) -> DocsSyncResponse:
    """Run the manifest-based sync + cache recreation pipeline."""
    try:
        result = await docs_sync.sync(payload)
    except SyncLockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DocsSyncService.diff_to_response(result)


__all__ = ["router"]
