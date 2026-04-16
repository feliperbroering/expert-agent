"""`/ask` — SSE streaming generation endpoint.

Flow (§6.2 of the plan):

1. Orchestrator builds `Content` list (recall + short buffer + user message).
2. Stream tokens via `llm.generate_stream`.
3. Persist the turn (Firestore + MemPalace async) after the stream completes.
4. On `CacheNotFoundError`, recreate the cache once and retry.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from ..auth import AuthenticatedUser
from ..deps import CacheManagerDep, LLMClientDep, OrchestratorDep
from ..llm.protocol import (
    CacheNotFoundError,
    CacheRef,
    Citation,
    GenerationChunk,
    Usage,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stream: bool = True


class AskSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage | None = None
    request_id: str


@dataclass(slots=True)
class _Accumulator:
    """Accumulates chunks so we can persist the final turn."""

    text_parts: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    usage: Usage | None = None
    finish_reason: str | None = None

    def absorb(self, chunk: GenerationChunk) -> None:
        if chunk.text:
            self.text_parts.append(chunk.text)
        if chunk.citations:
            self.citations.extend(chunk.citations)
        if chunk.usage is not None:
            self.usage = chunk.usage
        if chunk.finish_reason:
            self.finish_reason = chunk.finish_reason

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


def _sse_event(event_type: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": event_type, "data": json.dumps(payload, ensure_ascii=False)}


def _citation_to_dict(citation: Citation) -> dict[str, Any]:
    return {
        "source_uri": citation.source_uri,
        "start_index": citation.start_index,
        "end_index": citation.end_index,
        "snippet": citation.snippet,
    }


def _usage_to_dict(usage: Usage | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_tokens": usage.cached_tokens,
    }


async def _generate_with_fallback(
    *,
    llm: Any,
    cache_manager: Any,
    contents: list[Any],
    grounding: bool,
) -> AsyncIterator[GenerationChunk]:
    """Call `llm.generate_stream` and retry once on CacheNotFoundError."""
    cache: CacheRef = await cache_manager.get_or_create()
    try:
        async for chunk in llm.generate_stream(cache=cache, contents=contents, grounding=grounding):
            yield chunk
        return
    except CacheNotFoundError:
        logger.warning("ask.cache_not_found", cache_name=cache.name)
        cache = await cache_manager.handle_cache_not_found()

    async for chunk in llm.generate_stream(cache=cache, contents=contents, grounding=grounding):
        yield chunk


@router.post("/ask")
async def ask(
    payload: AskRequest,
    user_id: AuthenticatedUser,
    llm: LLMClientDep,
    cache_manager: CacheManagerDep,
    orchestrator: OrchestratorDep,
) -> Any:
    """Main generation endpoint. Streams by default; falls back to JSON when `stream=False`."""
    if payload.user_id != user_id and user_id != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_id in body does not match authenticated principal",
        )

    request_id = uuid.uuid4().hex
    contents = await orchestrator.build_contents(
        user_id=payload.user_id,
        session_id=payload.session_id,
        user_message=payload.message,
    )

    if payload.stream:
        return EventSourceResponse(
            _stream_events(
                request_id=request_id,
                payload=payload,
                llm=llm,
                cache_manager=cache_manager,
                orchestrator=orchestrator,
                contents=contents,
            ),
            media_type="text/event-stream",
        )

    accumulator = _Accumulator()
    async for chunk in _generate_with_fallback(
        llm=llm, cache_manager=cache_manager, contents=contents, grounding=True
    ):
        accumulator.absorb(chunk)

    await orchestrator.persist_turn(
        user_id=payload.user_id,
        session_id=payload.session_id,
        user_message=payload.message,
        assistant_message=accumulator.text,
        usage=accumulator.usage,
    )

    return AskSyncResponse(
        text=accumulator.text,
        citations=accumulator.citations,
        usage=accumulator.usage,
        request_id=request_id,
    )


async def _stream_events(
    *,
    request_id: str,
    payload: AskRequest,
    llm: Any,
    cache_manager: Any,
    orchestrator: Any,
    contents: list[Any],
) -> AsyncIterator[dict[str, str]]:
    accumulator = _Accumulator()
    started = time.perf_counter()
    try:
        async for chunk in _generate_with_fallback(
            llm=llm,
            cache_manager=cache_manager,
            contents=contents,
            grounding=True,
        ):
            accumulator.absorb(chunk)
            if chunk.text:
                yield _sse_event(
                    "token",
                    {"type": "token", "text": chunk.text, "request_id": request_id},
                )
            for citation in chunk.citations:
                yield _sse_event(
                    "citation",
                    {
                        "type": "citation",
                        "request_id": request_id,
                        **_citation_to_dict(citation),
                    },
                )
    except Exception as exc:
        logger.exception("ask.stream_failed", request_id=request_id, error=str(exc))
        yield _sse_event(
            "error",
            {"type": "error", "request_id": request_id, "detail": str(exc)},
        )
        return
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            await orchestrator.persist_turn(
                user_id=payload.user_id,
                session_id=payload.session_id,
                user_message=payload.message,
                assistant_message=accumulator.text,
                usage=accumulator.usage,
            )
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning(
                "ask.persist_failed",
                request_id=request_id,
                error=str(exc),
            )
        logger.info(
            "ask.complete",
            request_id=request_id,
            user_id=payload.user_id,
            session_id=payload.session_id,
            latency_ms=latency_ms,
            tokens_input=accumulator.usage.input_tokens if accumulator.usage else None,
            tokens_output=accumulator.usage.output_tokens if accumulator.usage else None,
            tokens_cached=accumulator.usage.cached_tokens if accumulator.usage else None,
        )

    yield _sse_event(
        "done",
        {
            "type": "done",
            "request_id": request_id,
            "finish_reason": accumulator.finish_reason,
            "usage": _usage_to_dict(accumulator.usage),
            "citations": [_citation_to_dict(c) for c in accumulator.citations],
        },
    )


__all__ = ["AskRequest", "AskSyncResponse", "router"]
