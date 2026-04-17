"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.config import Settings, get_settings
from app.llm.protocol import (
    CacheRef,
    Content,
    FileRef,
    GenerationChunk,
    LLMClient,
    Usage,
)
from app.schema import AgentSchema

EXAMPLE_SCHEMA = Path(__file__).resolve().parents[2] / "example-schema" / "agent_schema.yaml"


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AGENT_ID", "example-expert")
    monkeypatch.setenv("ADMIN_KEY", "admin-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("DOCS_BUCKET", "test-docs-bucket")
    monkeypatch.setenv("BACKUPS_BUCKET", "test-backups-bucket")
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("MEMPALACE_CHROMA_HOST", "localhost")
    monkeypatch.setenv("MEMPALACE_CHROMA_PORT", "8000")
    monkeypatch.setenv("MEMPALACE_CHROMA_SSL", "false")
    monkeypatch.setenv("SCHEMA_PATH", str(EXAMPLE_SCHEMA))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def schema() -> AgentSchema:
    return AgentSchema.from_yaml(EXAMPLE_SCHEMA)


@pytest.fixture
def firestore_mock() -> Any:
    from mockfirestore import MockFirestore

    return MockFirestore()


@pytest.fixture
def fake_llm_cls() -> type[FakeLLM]:
    """Expose the `FakeLLM` class to tests without relying on
    `from tests.conftest import ...`, which doesn't work under
    `--import-mode=importlib`.
    """
    return FakeLLM


class FakeLLM:
    """In-memory stand-in for `LLMClient`. Used across tests."""

    model = "gemini-fake"

    def __init__(self) -> None:
        self.created_caches: list[tuple[list[FileRef], str, int]] = []
        self.deleted_caches: list[str] = []
        self.ttl_updates: list[tuple[str, int]] = []
        self.tokens_counted: list[str] = []
        self.stream_chunks: list[GenerationChunk] = [
            GenerationChunk(text="Hello", finish_reason=None),
            GenerationChunk(text=" world", finish_reason=None),
            GenerationChunk(
                text="!",
                finish_reason="STOP",
                usage=Usage(input_tokens=5, output_tokens=3, cached_tokens=2),
            ),
        ]
        self._cache_counter = 0
        self.raise_cache_not_found_once = False
        self.closed = False

    def _make_cache(self) -> CacheRef:
        self._cache_counter += 1
        return CacheRef(
            name=f"cachedContents/{self._cache_counter:04d}",
            expire_time=datetime.now(tz=UTC) + timedelta(hours=1),
            model=self.model,
        )

    async def create_cache(
        self, docs: list[FileRef], system_instruction: str, ttl_seconds: int
    ) -> CacheRef:
        self.created_caches.append((list(docs), system_instruction, ttl_seconds))
        return self._make_cache()

    async def update_cache_ttl(self, cache: CacheRef, ttl_seconds: int) -> None:
        self.ttl_updates.append((cache.name, ttl_seconds))

    async def delete_cache(self, cache: CacheRef) -> None:
        self.deleted_caches.append(cache.name)

    async def count_tokens(self, text: str) -> int:
        self.tokens_counted.append(text)
        return max(1, len(text) // 4)

    async def close(self) -> None:
        self.closed = True

    async def generate_stream(
        self,
        cache: CacheRef,
        contents: list[Content],
        *,
        grounding: bool = True,
    ) -> AsyncIterator[GenerationChunk]:
        from app.llm.protocol import CacheNotFoundError

        if self.raise_cache_not_found_once:
            self.raise_cache_not_found_once = False
            raise CacheNotFoundError("cache expired")
        for chunk in self.stream_chunks:
            yield chunk


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def ensure_admin_env() -> None:
    os.environ.setdefault("ADMIN_KEY", "admin-secret")


@pytest.fixture
def llm_protocol_compat(fake_llm: FakeLLM) -> LLMClient:
    """Type-safety check that the fake conforms to the Protocol."""
    assert isinstance(fake_llm, LLMClient)
    return fake_llm
