"""Provider-agnostic interface for the LLM backend.

Both `GeminiAIStudioClient` and `GeminiVertexClient` (and future providers)
implement `LLMClient`. The rest of the backend only depends on this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


class CacheNotFoundError(RuntimeError):
    """Raised when the Gemini backend reports a stale/missing cached content.

    The `/ask` handler catches this to trigger a single on-demand recreation.
    """


@dataclass(frozen=True, slots=True)
class FileRef:
    """Reference to a document stored in GCS."""

    gcs_uri: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class CacheRef:
    """Reference to a Gemini Context Cache resource."""

    name: str
    expire_time: datetime
    model: str


@dataclass(slots=True)
class ContentPart:
    """A single text part of a `Content` turn."""

    text: str | None = None


@dataclass(slots=True)
class Content:
    """A conversation turn in the Gemini format."""

    role: str
    parts: list[ContentPart]


@dataclass(slots=True)
class Citation:
    """A grounded citation pointing back to a source document or URL."""

    source_uri: str
    start_index: int
    end_index: int
    snippet: str


@dataclass(slots=True)
class Usage:
    """Token accounting for a single generation."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int


@dataclass(slots=True)
class GenerationChunk:
    """One streamed delta returned by `LLMClient.generate_stream`."""

    text: str
    finish_reason: str | None = None
    citations: list[Citation] = field(default_factory=list)
    usage: Usage | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Async interface every LLM provider must implement."""

    async def create_cache(
        self,
        docs: list[FileRef],
        system_instruction: str,
        ttl_seconds: int,
    ) -> CacheRef: ...

    async def update_cache_ttl(self, cache: CacheRef, ttl_seconds: int) -> None: ...

    async def delete_cache(self, cache: CacheRef) -> None: ...

    def generate_stream(
        self,
        cache: CacheRef,
        contents: list[Content],
        *,
        grounding: bool = True,
    ) -> AsyncIterator[GenerationChunk]: ...

    async def count_tokens(self, text: str) -> int: ...

    async def close(self) -> None: ...


__all__ = [
    "CacheNotFoundError",
    "CacheRef",
    "Citation",
    "Content",
    "ContentPart",
    "FileRef",
    "GenerationChunk",
    "LLMClient",
    "Usage",
]
