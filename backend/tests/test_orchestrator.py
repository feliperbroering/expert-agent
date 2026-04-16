"""Tests for the memory orchestrator composition and trim logic."""

from __future__ import annotations

import asyncio

import pytest
from app.llm.protocol import Usage
from app.memory.long_term import LongTermMemory, MemoryHit
from app.memory.orchestrator import (
    RECALL_FOOTER,
    RECALL_HEADER,
    MemoryOrchestrator,
)
from app.memory.short_term import ShortTermMemory


class _StubBackend:
    def __init__(self) -> None:
        self.remembered: list[dict[str, str]] = []
        self.hits: list[MemoryHit] = []

    async def remember(self, *, wing: str, hall: str, room: str, drawer: str, content: str) -> None:
        self.remembered.append(
            {"wing": wing, "hall": hall, "room": room, "drawer": drawer, "content": content}
        )

    async def search(self, *, query: str, wing: str, k: int) -> list[MemoryHit]:
        return list(self.hits[:k])

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_build_contents_orders_recall_then_buffer_then_current(firestore_mock) -> None:
    short = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)
    await short.append_turn(user_id="u", session_id="s", user_msg="q0", assistant_msg="a0")

    backend = _StubBackend()
    backend.hits = [MemoryHit(id="m1", text="past fact", score=0.9)]
    long_term = LongTermMemory(collection_name="test", backend=backend)

    orch = MemoryOrchestrator(
        short_term=short,
        long_term=long_term,
        buffer_size=20,
        max_recall_results=5,
    )

    contents = await orch.build_contents(user_id="u", session_id="s", user_message="what about q1?")

    recall = contents[0].parts[0].text or ""
    assert RECALL_HEADER in recall
    assert RECALL_FOOTER in recall
    assert "past fact" in recall
    assert contents[1].parts[0].text == "q0"
    assert contents[2].parts[0].text == "a0"
    assert contents[-1].parts[0].text == "what about q1?"


@pytest.mark.asyncio
async def test_build_contents_trims_recall_when_over_budget(firestore_mock) -> None:
    short = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)

    backend = _StubBackend()
    # Each hit is 1000 chars => ~250 tokens; 10 hits should blow a 1000-token budget.
    backend.hits = [MemoryHit(id=f"m{i}", text="x" * 1000, score=0.1) for i in range(10)]
    long_term = LongTermMemory(collection_name="test", backend=backend)

    orch = MemoryOrchestrator(
        short_term=short,
        long_term=long_term,
        buffer_size=20,
        max_recall_results=10,
        budget_tokens=200,
    )

    contents = await orch.build_contents(user_id="u", session_id="s", user_message="tiny message")

    # Either recall got fully dropped or drastically pruned.
    recall_text = contents[0].parts[0].text or ""
    if RECALL_HEADER in recall_text:
        assert recall_text.count("Memory ") <= 2
    else:
        assert recall_text == "tiny message"


@pytest.mark.asyncio
async def test_persist_turn_writes_firestore_and_dispatches_remember(firestore_mock) -> None:
    short = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)
    backend = _StubBackend()
    long_term = LongTermMemory(collection_name="test", backend=backend)

    orch = MemoryOrchestrator(short_term=short, long_term=long_term)

    await orch.persist_turn(
        user_id="u",
        session_id="s",
        user_message="ping",
        assistant_message="pong",
        usage=Usage(input_tokens=1, output_tokens=1, cached_tokens=0),
    )

    # Wait for the async remember() to drain.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    buffer = await short.get_buffer(user_id="u", session_id="s", n=10)
    assert len(buffer) == 2
    assert backend.remembered, "MemPalace remember() was not invoked"
    assert "ping" in backend.remembered[0]["content"]
    assert "pong" in backend.remembered[0]["content"]
