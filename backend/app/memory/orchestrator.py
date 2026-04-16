"""Composes the `Content` list fed to Gemini for each /ask request.

Order (per §7.4 of the plan):

1. Short-term buffer (Firestore, last N messages).
2. Long-term recall (MemPalace top-K) — injected as a "Relevant past
   conversation" user-role turn *before* the short buffer.
3. The current user message.

`persist_turn` writes to both Firestore and MemPalace; the MemPalace write is
fire-and-forget so it never blocks the response.
"""

from __future__ import annotations

import asyncio

import structlog

from ..llm.protocol import Content, ContentPart, LLMClient, Usage
from .long_term import LongTermMemory, MemoryHit
from .short_term import ShortTermMemory

logger = structlog.get_logger(__name__)

RECALL_HEADER = "## Relevant past conversation"
RECALL_FOOTER = "## End of past conversation"
# Hard cap on the total prompt size (short buffer + recall + current message).
# Gemini 3.1 Pro has a 1M window but we keep the moving parts well below it.
DEFAULT_BUDGET_TOKENS = 80_000


class MemoryOrchestrator:
    """Assembles prompt `Content` and persists turns to both memory layers."""

    def __init__(
        self,
        *,
        short_term: ShortTermMemory,
        long_term: LongTermMemory | None,
        llm: LLMClient | None = None,
        buffer_size: int = 20,
        max_recall_results: int = 5,
        budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    ) -> None:
        self._short_term = short_term
        self._long_term = long_term
        self._llm = llm
        self._buffer_size = buffer_size
        self._max_recall = max_recall_results
        self._budget_tokens = budget_tokens

    async def build_contents(
        self, *, user_id: str, session_id: str, user_message: str
    ) -> list[Content]:
        """Return the ordered list of `Content` turns for the next generation."""
        buffer = await self._short_term.get_buffer(
            user_id=user_id, session_id=session_id, n=self._buffer_size
        )

        recall: list[MemoryHit] = []
        if self._long_term is not None and self._max_recall > 0:
            try:
                recall = await self._long_term.search(
                    query=user_message, user_id=user_id, k=self._max_recall
                )
            except Exception as exc:
                logger.warning("orchestrator.recall_failed", error=str(exc))

        recall_turn: Content | None = _recall_to_content(recall)
        current_turn = Content(role="user", parts=[ContentPart(text=user_message)])

        contents = self._trim_to_budget(
            recall_turn=recall_turn,
            buffer=buffer,
            current=current_turn,
            recall_hits=recall,
        )
        return contents

    def _trim_to_budget(
        self,
        *,
        recall_turn: Content | None,
        buffer: list[Content],
        current: Content,
        recall_hits: list[MemoryHit],
    ) -> list[Content]:
        """Drop recall progressively (then buffer) when the estimate exceeds the budget."""
        contents: list[Content] = []
        if recall_turn is not None:
            contents.append(recall_turn)
        contents.extend(buffer)
        contents.append(current)

        if self._estimate_tokens(contents) <= self._budget_tokens:
            return contents

        # Step 1: shrink recall hits one by one.
        pruned_hits = list(recall_hits)
        while pruned_hits and recall_turn is not None:
            pruned_hits.pop()
            new_recall = _recall_to_content(pruned_hits)
            contents = []
            if new_recall is not None:
                contents.append(new_recall)
            contents.extend(buffer)
            contents.append(current)
            recall_turn = new_recall
            if self._estimate_tokens(contents) <= self._budget_tokens:
                return contents

        # Step 2: drop oldest buffer messages as a last resort.
        trimmed_buffer = list(buffer)
        while trimmed_buffer and self._estimate_tokens(contents) > self._budget_tokens:
            trimmed_buffer.pop(0)
            contents = []
            if recall_turn is not None:
                contents.append(recall_turn)
            contents.extend(trimmed_buffer)
            contents.append(current)

        logger.warning(
            "orchestrator.trimmed",
            buffer_kept=len(trimmed_buffer),
            recall_kept=len(pruned_hits),
            budget_tokens=self._budget_tokens,
        )
        return contents

    def _estimate_tokens(self, contents: list[Content]) -> int:
        """Cheap char-based estimate (4 chars/token). Avoids paying for count_tokens."""
        total = 0
        for content in contents:
            for part in content.parts:
                if part.text is None:
                    continue
                total += max(1, len(part.text) // 4)
        return total

    async def persist_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        usage: Usage | None = None,
    ) -> None:
        """Write to Firestore synchronously; dispatch MemPalace write in background."""
        _user_msg_id, model_msg_id = await self._short_term.append_turn(
            user_id=user_id,
            session_id=session_id,
            user_msg=user_message,
            assistant_msg=assistant_message,
            usage=usage,
        )

        if self._long_term is None:
            return

        verbatim = _format_turn_for_recall(user_message, assistant_message)
        task = asyncio.create_task(
            self._safe_remember(
                user_id=user_id,
                session_id=session_id,
                msg_id=model_msg_id,
                content=verbatim,
            )
        )
        task.add_done_callback(self._log_task_exception)

    async def _safe_remember(
        self, *, user_id: str, session_id: str, msg_id: str, content: str
    ) -> None:
        assert self._long_term is not None
        try:
            await self._long_term.remember(
                user_id=user_id,
                session_id=session_id,
                msg_id=msg_id,
                content=content,
            )
        except Exception as exc:
            logger.warning(
                "orchestrator.remember_failed",
                user_id=user_id,
                session_id=session_id,
                error=str(exc),
            )

    @staticmethod
    def _log_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:  # pragma: no cover - already logged in _safe_remember
            logger.warning("orchestrator.background_task_error", error=str(exc))


def _recall_to_content(hits: list[MemoryHit]) -> Content | None:
    if not hits:
        return None
    lines = [RECALL_HEADER]
    for i, hit in enumerate(hits, start=1):
        lines.append(f"### Memory {i} (score={hit.score:.3f})")
        lines.append(hit.text.strip())
    lines.append(RECALL_FOOTER)
    return Content(role="user", parts=[ContentPart(text="\n\n".join(lines))])


def _format_turn_for_recall(user_message: str, assistant_message: str) -> str:
    return f"User: {user_message.strip()}\n\nAssistant: {assistant_message.strip()}"


__all__ = ["RECALL_FOOTER", "RECALL_HEADER", "MemoryOrchestrator"]
