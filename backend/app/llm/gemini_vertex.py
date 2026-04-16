"""Stub for the Vertex AI flavour of the Gemini client.

The Vertex backend will ship in v0.2 — see the project roadmap. For now the
class exists so the Protocol stays pluggable and the factory can raise a
deterministic error when a schema selects `provider: gemini-vertex`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .protocol import CacheRef, Content, FileRef, GenerationChunk


class GeminiVertexClient:
    """Placeholder implementation for the Vertex AI backend."""

    def __init__(self, *_: Any, **__: Any) -> None:  # pragma: no cover - trivial
        raise NotImplementedError("Vertex client coming in v0.2")

    async def create_cache(  # pragma: no cover - trivial
        self,
        docs: list[FileRef],
        system_instruction: str,
        ttl_seconds: int,
    ) -> CacheRef:
        raise NotImplementedError("Vertex client coming in v0.2")

    async def update_cache_ttl(  # pragma: no cover - trivial
        self, cache: CacheRef, ttl_seconds: int
    ) -> None:
        raise NotImplementedError("Vertex client coming in v0.2")

    async def delete_cache(  # pragma: no cover - trivial
        self, cache: CacheRef
    ) -> None:
        raise NotImplementedError("Vertex client coming in v0.2")

    def generate_stream(  # pragma: no cover - trivial
        self,
        cache: CacheRef,
        contents: list[Content],
        *,
        grounding: bool = True,
    ) -> AsyncIterator[GenerationChunk]:
        raise NotImplementedError("Vertex client coming in v0.2")

    async def count_tokens(self, text: str) -> int:  # pragma: no cover - trivial
        raise NotImplementedError("Vertex client coming in v0.2")

    async def close(self) -> None:  # pragma: no cover - trivial
        raise NotImplementedError("Vertex client coming in v0.2")


__all__ = ["GeminiVertexClient"]
