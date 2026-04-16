"""Integration test for the /ask SSE streaming endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.cache.manager import CacheManager
from app.docs.manifest import FileEntry, SyncManifest
from app.llm.protocol import CacheRef
from app.main import create_app
from app.memory.long_term import LongTermMemory, MemoryHit
from app.memory.orchestrator import MemoryOrchestrator
from app.memory.short_term import ShortTermMemory
from fastapi.testclient import TestClient


class _StubLongTermBackend:
    async def remember(self, *, wing: str, hall: str, room: str, drawer: str, content: str) -> None:
        return None

    async def search(self, *, query: str, wing: str, k: int) -> list[MemoryHit]:
        return []

    async def close(self) -> None:
        return None


def _wire_app(app, firestore_mock, fake_llm) -> None:
    schema = app.state.schema
    short = ShortTermMemory(agent_id=schema.agent_id, firestore_client=firestore_mock)
    long_term = LongTermMemory(collection_name="test", backend=_StubLongTermBackend())
    entry = FileEntry(
        sha256="a" * 64,
        size=10,
        gcs_uri="gs://bucket/example-expert/aa/file.md",
        mime_type="text/markdown",
        updated_at=datetime.now(tz=UTC),
    )
    manifest = SyncManifest(files={"file.md": entry})

    async def _loader() -> SyncManifest:
        return manifest

    cache_manager = CacheManager(
        agent_id=schema.agent_id,
        llm=fake_llm,
        firestore_client=firestore_mock,
        system_instruction="sys",
        ttl_seconds=3600,
        manifest_loader=_loader,
    )

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(cache_manager.get_or_create(manifest))
    finally:
        loop.close()

    orchestrator = MemoryOrchestrator(
        short_term=short,
        long_term=long_term,
        buffer_size=20,
        max_recall_results=5,
    )

    app.state.llm = fake_llm
    app.state.firestore_client = firestore_mock
    app.state.cache_manager = cache_manager
    app.state.short_term = short
    app.state.long_term = long_term
    app.state.orchestrator = orchestrator


@pytest.fixture
def client_with_stubs(firestore_mock, fake_llm):
    app = create_app()
    with TestClient(app) as client:
        _wire_app(app, firestore_mock, fake_llm)
        yield client, app


def test_ask_streams_sse_tokens_and_persists_turn(client_with_stubs) -> None:
    client, app = client_with_stubs

    with client.stream(
        "POST",
        "/ask",
        json={
            "user_id": "user-1",
            "session_id": "sess-1",
            "message": "Hi there",
            "stream": True,
        },
        headers={"Authorization": "Bearer admin-secret"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    # SSE stream contains a token event and a done event.
    assert "event: token" in body
    assert "event: done" in body
    # Our FakeLLM streams "Hello", " world", "!" — the concatenation should be in an SSE line.
    assert '"text": "Hello"' in body
    assert '"text": " world"' in body

    short: ShortTermMemory = app.state.short_term
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        messages = loop.run_until_complete(
            short.get_buffer(user_id="user-1", session_id="sess-1", n=10)
        )
    finally:
        loop.close()

    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].parts[0].text == "Hi there"
    assert messages[1].role == "model"
    assert messages[1].parts[0].text == "Hello world!"


def test_ask_non_stream_returns_json(client_with_stubs) -> None:
    client, _app = client_with_stubs

    resp = client.post(
        "/ask",
        json={
            "user_id": "user-1",
            "session_id": "sess-2",
            "message": "Sync version",
            "stream": False,
        },
        headers={"Authorization": "Bearer admin-secret"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Hello world!"
    assert body["usage"]["input_tokens"] == 5


def test_ask_requires_auth(client_with_stubs) -> None:
    client, _app = client_with_stubs
    resp = client.post(
        "/ask",
        json={"user_id": "u", "session_id": "s", "message": "hi"},
    )
    assert resp.status_code == 401


def test_ask_recreates_cache_on_cache_not_found(client_with_stubs, fake_llm) -> None:
    client, _app = client_with_stubs
    fake_llm.raise_cache_not_found_once = True

    resp = client.post(
        "/ask",
        json={
            "user_id": "user-1",
            "session_id": "sess-3",
            "message": "retry",
            "stream": False,
        },
        headers={"Authorization": "Bearer admin-secret"},
    )
    # After the CacheNotFound once, the retry succeeds.
    assert resp.status_code == 200
    assert resp.json()["text"] == "Hello world!"


def test_cache_ref_is_exported() -> None:
    # Smoke: ensure CacheRef import path stays stable for callers.
    cache = CacheRef(
        name="cachedContents/x",
        expire_time=datetime.now(tz=UTC) + timedelta(hours=1),
        model="gemini-test",
    )
    assert cache.name.startswith("cachedContents/")
