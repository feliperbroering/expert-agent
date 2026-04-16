"""Tests for the Firestore-backed short-term buffer."""

from __future__ import annotations

import pytest
from app.llm.protocol import Usage
from app.memory.short_term import ShortTermMemory


@pytest.mark.asyncio
async def test_append_turn_persists_both_messages_and_updates_session(firestore_mock) -> None:
    memory = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)

    await memory.append_turn(
        user_id="user-1",
        session_id="sess-1",
        user_msg="hello?",
        assistant_msg="hi!",
        usage=Usage(input_tokens=10, output_tokens=3, cached_tokens=0),
    )

    session_doc = (
        firestore_mock.collection("agents")
        .document("example-expert")
        .collection("users")
        .document("user-1")
        .collection("sessions")
        .document("sess-1")
        .get()
        .to_dict()
    )
    assert session_doc["message_count"] == 2
    assert session_doc["title"] == "hello?"

    messages = list(
        firestore_mock.collection("agents")
        .document("example-expert")
        .collection("users")
        .document("user-1")
        .collection("sessions")
        .document("sess-1")
        .collection("messages")
        .stream()
    )
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_get_buffer_returns_chronological_order(firestore_mock) -> None:
    memory = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)

    for i in range(3):
        await memory.append_turn(
            user_id="user-1",
            session_id="sess-1",
            user_msg=f"q{i}",
            assistant_msg=f"a{i}",
        )

    buffer = await memory.get_buffer(user_id="user-1", session_id="sess-1", n=20)
    texts = [c.parts[0].text for c in buffer]
    roles = [c.role for c in buffer]

    assert len(buffer) == 6
    assert texts == ["q0", "a0", "q1", "a1", "q2", "a2"]
    assert roles == ["user", "model"] * 3


@pytest.mark.asyncio
async def test_get_buffer_limits_to_n(firestore_mock) -> None:
    memory = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)
    for i in range(5):
        await memory.append_turn(
            user_id="u", session_id="s", user_msg=f"q{i}", assistant_msg=f"a{i}"
        )
    buffer = await memory.get_buffer(user_id="u", session_id="s", n=3)
    assert len(buffer) == 3
    # Latest entries, chronological.
    assert [c.parts[0].text for c in buffer] == ["a3", "q4", "a4"]


@pytest.mark.asyncio
async def test_delete_session_removes_everything(firestore_mock) -> None:
    memory = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)
    for i in range(2):
        await memory.append_turn(
            user_id="u", session_id="s", user_msg=f"q{i}", assistant_msg=f"a{i}"
        )

    removed = await memory.delete_session(user_id="u", session_id="s")
    assert removed == 4
    buffer = await memory.get_buffer(user_id="u", session_id="s", n=10)
    assert buffer == []


@pytest.mark.asyncio
async def test_list_sessions_returns_summaries(firestore_mock) -> None:
    memory = ShortTermMemory(agent_id="example-expert", firestore_client=firestore_mock)
    await memory.append_turn(user_id="u", session_id="s1", user_msg="a", assistant_msg="b")
    await memory.append_turn(user_id="u", session_id="s2", user_msg="c", assistant_msg="d")

    sessions = await memory.list_sessions(user_id="u")
    ids = {s.session_id for s in sessions}
    assert ids == {"s1", "s2"}
    assert all(s.message_count == 2 for s in sessions)
