"""Per-user session management for short-term memory.

LGPD/GDPR: `DELETE /sessions/{id}` implements right-to-erasure. Users can
only touch their own sessions unless the bearer token is the admin key.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from ..auth import AuthenticatedUser
from ..deps import ShortTermDep
from ..memory.short_term import SessionSummary

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _resolve_user_id(user_id_param: str | None, principal: str) -> str:
    if principal == "admin":
        if not user_id_param:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="admin token requires `user_id` query parameter",
            )
        return user_id_param
    if user_id_param and user_id_param != principal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot access other users' sessions",
        )
    return principal


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    principal: AuthenticatedUser,
    short_term: ShortTermDep,
    user_id: str | None = Query(default=None),
) -> list[SessionSummary]:
    effective = _resolve_user_id(user_id, principal)
    return await short_term.list_sessions(user_id=effective)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    principal: AuthenticatedUser,
    short_term: ShortTermDep,
    user_id: str | None = Query(default=None),
) -> dict[str, Any]:
    effective = _resolve_user_id(user_id, principal)
    messages = await short_term.get_buffer(user_id=effective, session_id=session_id, n=100)
    return {
        "session_id": session_id,
        "user_id": effective,
        "messages": [
            {
                "role": m.role,
                "content": m.parts[0].text if m.parts else "",
            }
            for m in messages
        ],
    }


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    principal: AuthenticatedUser,
    short_term: ShortTermDep,
    user_id: str | None = Query(default=None),
) -> dict[str, Any]:
    effective = _resolve_user_id(user_id, principal)
    deleted = await short_term.delete_session(user_id=effective, session_id=session_id)
    return {"session_id": session_id, "messages_deleted": deleted}


__all__ = ["router"]
