"""`/health` and `/ready` endpoints — public, used for liveness/readiness probes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from .. import __version__
from ..config import Settings, get_settings
from ..deps import AgentSchemaDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    schema: AgentSchemaDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Liveness — no dependency checks, returns 200 as long as the app is up."""
    return {
        "status": "ok",
        "agent_id": schema.agent_id,
        "version": __version__,
        "model": schema.spec.model.name,
        "env": settings.app_env,
    }


@router.get("/ready")
async def ready(request: Request, schema: AgentSchemaDep) -> dict[str, Any]:
    """Readiness — probes every external dependency that `/ask` needs.

    Failures are reported per-component so probes can decide whether to
    fail-closed or allow partial degradation.
    """
    checks: dict[str, str] = {}

    llm = getattr(request.app.state, "llm", None)
    checks["llm"] = "ok" if llm is not None else "unavailable"

    firestore = getattr(request.app.state, "firestore_client", None)
    checks["firestore"] = "ok" if firestore is not None else "unavailable"

    long_term = getattr(request.app.state, "long_term", None)
    checks["chroma"] = "ok" if long_term is not None else "disabled"

    all_ok = all(v in {"ok", "disabled"} for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "agent_id": schema.agent_id,
        "checks": checks,
    }


__all__ = ["router"]
