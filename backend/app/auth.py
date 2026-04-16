"""FastAPI dependencies for Bearer-token authentication.

Admin auth is a literal comparison against the `ADMIN_KEY` secret. User auth
looks up a bcrypt hash stored in Firestore at
`agents/{agent_id}/users/{uid}/api_key_hash`.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Protocol

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


class _UserStore(Protocol):
    """Minimal protocol so tests can inject a fake user store."""

    async def lookup_bcrypt_hash(self, agent_id: str, token: str) -> tuple[str, bytes] | None:
        """Return `(user_id, bcrypt_hash)` for the first matching user or None."""


def _constant_time_equal(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _extract_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Require the configured admin key. Returns the literal `"admin"` subject."""
    token = _extract_token(credentials)
    expected = settings.admin_key.get_secret_value()
    if not expected or not _constant_time_equal(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "admin"


async def require_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Resolve the caller's `user_id` by matching the bearer token.

    The admin key is also accepted (useful for debugging); in that case the
    returned `user_id` is `"admin"`.
    """
    token = _extract_token(credentials)

    admin_key = settings.admin_key.get_secret_value()
    if admin_key and _constant_time_equal(token, admin_key):
        return "admin"

    store: _UserStore | None = getattr(request.app.state, "user_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User store not configured",
        )

    match = await store.lookup_bcrypt_hash(settings.agent_id, token)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id, hashed = match
    if not bcrypt.checkpw(token.encode("utf-8"), hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


AdminUser = Annotated[str, Depends(require_admin)]
AuthenticatedUser = Annotated[str, Depends(require_user)]


__all__ = [
    "AdminUser",
    "AuthenticatedUser",
    "require_admin",
    "require_user",
]
