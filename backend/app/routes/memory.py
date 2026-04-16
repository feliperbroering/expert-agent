"""Admin-only debug endpoint for raw MemPalace search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..auth import AdminUser
from ..deps import LongTermDep
from ..memory.long_term import MemoryHit

router = APIRouter(prefix="/memory", tags=["memory"])


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)


class MemorySearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hits: list[MemoryHit]


@router.post("/search", response_model=MemorySearchResponse)
async def memory_search(
    payload: MemorySearchRequest,
    long_term: LongTermDep,
    _: AdminUser,
) -> MemorySearchResponse:
    if long_term is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="long-term memory disabled",
        )
    hits = await long_term.search(query=payload.query, user_id=payload.user_id, k=payload.k)
    return MemorySearchResponse(hits=hits)


__all__ = ["router"]
