"""Firestore-backed short-term conversational buffer.

Layout::

    agents/{agent_id}/users/{user_id}/sessions/{session_id}
                                                 └── messages/{msg_id}

Session document fields: `created_at`, `updated_at`, `title`, `message_count`.
Message document fields: `role` (user|model), `content`, `created_at`,
`tokens_input`, `tokens_output`.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from ..llm.protocol import Content, ContentPart, Usage

logger = structlog.get_logger(__name__)

Role = Literal["user", "model"]


class SessionSummary(BaseModel):
    """Lightweight session view used by `/sessions`."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    title: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message_count: int = Field(default=0, ge=0)


@dataclass(slots=True)
class StoredMessage:
    """Internal representation of a persisted message."""

    msg_id: str
    role: Role
    content: str
    created_at: datetime
    tokens_input: int = 0
    tokens_output: int = 0


class ShortTermMemory:
    """Firestore wrapper for conversational turns."""

    def __init__(self, *, agent_id: str, firestore_client: Any) -> None:
        self._agent_id = agent_id
        self._firestore = firestore_client

    def _session_ref(self, user_id: str, session_id: str) -> Any:
        return (
            self._firestore.collection("agents")
            .document(self._agent_id)
            .collection("users")
            .document(user_id)
            .collection("sessions")
            .document(session_id)
        )

    def _sessions_ref(self, user_id: str) -> Any:
        return (
            self._firestore.collection("agents")
            .document(self._agent_id)
            .collection("users")
            .document(user_id)
            .collection("sessions")
        )

    def _messages_ref(self, user_id: str, session_id: str) -> Any:
        return self._session_ref(user_id, session_id).collection("messages")

    async def append_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        usage: Usage | None = None,
    ) -> tuple[str, str]:
        """Persist both halves of a turn atomically. Returns `(user_msg_id, model_msg_id)`."""
        now = datetime.now(tz=UTC)
        user_msg_id = _timestamped_id(now)
        model_msg_id = _timestamped_id(now, offset_us=1)
        tokens_in = usage.input_tokens if usage else 0
        tokens_out = usage.output_tokens if usage else 0

        def _write() -> None:
            session_ref = self._session_ref(user_id, session_id)
            # Read BEFORE touching the messages subcollection: some Firestore
            # test doubles auto-create the parent document when a subcollection
            # is accessed.
            snap = session_ref.get()
            existing = (
                snap.to_dict()
                if getattr(snap, "exists", False) and (snap.to_dict() or {}).get("created_at")
                else None
            )
            messages_ref = self._messages_ref(user_id, session_id)

            prior_count = int(existing.get("message_count", 0)) if existing else 0
            title = existing.get("title", "") if existing else user_msg[:80].strip()
            created_at = existing.get("created_at", now) if existing else now

            writes: list[tuple[Any, dict[str, Any], bool]] = [
                (
                    session_ref,
                    {
                        "created_at": created_at,
                        "updated_at": now,
                        "title": title,
                        "message_count": prior_count + 2,
                    },
                    True,
                ),
                (
                    messages_ref.document(user_msg_id),
                    {
                        "role": "user",
                        "content": user_msg,
                        "created_at": now,
                        "tokens_input": tokens_in,
                        "tokens_output": 0,
                    },
                    False,
                ),
                (
                    messages_ref.document(model_msg_id),
                    {
                        "role": "model",
                        "content": assistant_msg,
                        "created_at": now,
                        "tokens_input": 0,
                        "tokens_output": tokens_out,
                    },
                    False,
                ),
            ]

            batch_fn = getattr(self._firestore, "batch", None)
            if callable(batch_fn):
                batch = batch_fn()
                for ref, data, merge in writes:
                    if merge:
                        batch.set(ref, data, merge=True)
                    else:
                        batch.set(ref, data)
                batch.commit()
                return
            for ref, data, merge in writes:
                if merge:
                    ref.set(data, merge=True)
                else:
                    ref.set(data)

        await asyncio.to_thread(_write)
        logger.info(
            "short_term.append_turn",
            user_id=user_id,
            session_id=session_id,
            user_msg_id=user_msg_id,
            model_msg_id=model_msg_id,
        )
        return user_msg_id, model_msg_id

    async def get_buffer(self, *, user_id: str, session_id: str, n: int = 20) -> list[Content]:
        """Return the last `n` messages as `Content` objects in chronological order."""
        if n <= 0:
            return []

        def _read() -> list[StoredMessage]:
            messages_ref = self._messages_ref(user_id, session_id)
            docs = list(messages_ref.stream())
            parsed: list[StoredMessage] = []
            for doc in docs:
                data = doc.to_dict() or {}
                role = data.get("role", "user")
                if role not in ("user", "model"):
                    continue
                parsed.append(
                    StoredMessage(
                        msg_id=doc.id,
                        role=role,
                        content=str(data.get("content", "")),
                        created_at=_coerce_dt(data.get("created_at")),
                        tokens_input=int(data.get("tokens_input", 0) or 0),
                        tokens_output=int(data.get("tokens_output", 0) or 0),
                    )
                )
            parsed.sort(key=lambda m: (m.created_at, m.msg_id))
            return parsed[-n:]

        stored = await asyncio.to_thread(_read)
        return [Content(role=m.role, parts=[ContentPart(text=m.content)]) for m in stored]

    async def delete_session(self, *, user_id: str, session_id: str) -> int:
        """Delete a session and all its messages. Returns the count deleted."""

        def _delete() -> int:
            messages_ref = self._messages_ref(user_id, session_id)
            session_ref = self._session_ref(user_id, session_id)
            deleted = 0
            for doc in messages_ref.stream():
                messages_ref.document(doc.id).delete()
                deleted += 1
            session_ref.delete()
            return deleted

        removed = await asyncio.to_thread(_delete)
        logger.info(
            "short_term.delete_session",
            user_id=user_id,
            session_id=session_id,
            messages_deleted=removed,
        )
        return removed

    async def list_sessions(self, *, user_id: str) -> list[SessionSummary]:
        def _read() -> list[SessionSummary]:
            sessions = list(self._sessions_ref(user_id).stream())
            summaries: list[SessionSummary] = []
            for doc in sessions:
                data = doc.to_dict() or {}
                summaries.append(
                    SessionSummary(
                        session_id=doc.id,
                        title=str(data.get("title", "")),
                        created_at=_safe_dt(data.get("created_at")),
                        updated_at=_safe_dt(data.get("updated_at")),
                        message_count=int(data.get("message_count", 0) or 0),
                    )
                )
            summaries.sort(
                key=lambda s: s.updated_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )
            return summaries

        return await asyncio.to_thread(_read)


def _timestamped_id(now: datetime, *, offset_us: int = 0) -> str:
    """Monotonically-sortable message id: `<epoch_ms>-<short_uuid>`."""
    micros = int(now.timestamp() * 1_000_000) + offset_us
    return f"{micros:016d}-{uuid.uuid4().hex[:8]}"


def _coerce_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=UTC)


def _safe_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


__all__ = ["Role", "SessionSummary", "ShortTermMemory", "StoredMessage"]
