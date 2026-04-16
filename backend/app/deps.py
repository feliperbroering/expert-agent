"""FastAPI dependency providers.

Every long-lived singleton (LLM client, cache manager, memory orchestrator,
etc.) is attached to `app.state` by the lifespan in `main.py`. Route handlers
pull them via these dependencies, which keeps handlers easy to unit-test:
tests can populate `app.state` with fakes and the dependencies resolve them
automatically.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from .cache.manager import CacheManager
from .docs.sync import DocsSyncService
from .llm.protocol import LLMClient
from .memory.long_term import LongTermMemory
from .memory.orchestrator import MemoryOrchestrator
from .memory.short_term import ShortTermMemory
from .schema import AgentSchema


def _from_state[T](request: Request, attr: str, expected: type[T]) -> T:
    value = getattr(request.app.state, attr, None)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{attr} not initialised",
        )
    if not isinstance(value, expected):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{attr} has wrong type: {type(value).__name__}",
        )
    return value


def get_schema(request: Request) -> AgentSchema:
    return _from_state(request, "schema", AgentSchema)


def get_llm(request: Request) -> LLMClient:
    value = getattr(request.app.state, "llm", None)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm not initialised",
        )
    return value  # type: ignore[no-any-return]


def get_cache_manager(request: Request) -> CacheManager:
    return _from_state(request, "cache_manager", CacheManager)


def get_docs_sync(request: Request) -> DocsSyncService:
    return _from_state(request, "docs_sync", DocsSyncService)


def get_short_term(request: Request) -> ShortTermMemory:
    return _from_state(request, "short_term", ShortTermMemory)


def get_long_term(request: Request) -> LongTermMemory | None:
    return getattr(request.app.state, "long_term", None)


def get_orchestrator(request: Request) -> MemoryOrchestrator:
    return _from_state(request, "orchestrator", MemoryOrchestrator)


AgentSchemaDep = Annotated[AgentSchema, Depends(get_schema)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm)]
CacheManagerDep = Annotated[CacheManager, Depends(get_cache_manager)]
DocsSyncDep = Annotated[DocsSyncService, Depends(get_docs_sync)]
ShortTermDep = Annotated[ShortTermMemory, Depends(get_short_term)]
LongTermDep = Annotated[LongTermMemory | None, Depends(get_long_term)]
OrchestratorDep = Annotated[MemoryOrchestrator, Depends(get_orchestrator)]


__all__ = [
    "AgentSchemaDep",
    "CacheManagerDep",
    "DocsSyncDep",
    "LLMClientDep",
    "LongTermDep",
    "OrchestratorDep",
    "ShortTermDep",
    "get_cache_manager",
    "get_docs_sync",
    "get_llm",
    "get_long_term",
    "get_orchestrator",
    "get_schema",
    "get_short_term",
]
