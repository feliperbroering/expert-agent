"""Long-term verbatim recall via MemPalace + an HTTP Chroma backend.

MemPalace's storage API in its current public release targets a **local**
palace directory (`palace_path`). To keep the plan's Cloud Run deployment
working (stateless agents backed by a remote Chroma server) we wrap Chroma
directly and expose the MemPalace-style `wing/room/drawer` addressing.

TODO(expert-agent): switch to MemPalace's native HTTP/remote API once it
lands upstream. Tracking: https://github.com/milla-jovovich/mempalace/issues.
Until then this thin wrapper keeps the orchestrator agnostic of the underlying
vector store and is easy to mock in unit tests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)


class MemoryHit(BaseModel):
    """Single search result from long-term memory."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float = Field(default=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class _ChromaCollection(Protocol):
    """Protocol capturing the subset of Chroma's collection API we use."""

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    def query(
        self,
        *,
        query_texts: list[str],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class MemPalaceBackend(Protocol):
    """Abstraction over the palace so tests can mock it independently."""

    async def remember(
        self,
        *,
        wing: str,
        hall: str,
        room: str,
        drawer: str,
        content: str,
    ) -> None: ...

    async def search(
        self,
        *,
        query: str,
        wing: str,
        k: int,
    ) -> list[MemoryHit]: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class _ChromaBackend:
    """MemPalace-style backend implemented directly on top of Chroma.

    We keep the same wing/hall/room/drawer semantics as MemPalace so the public
    API doesn't have to change when we swap to the upstream library.
    """

    collection: _ChromaCollection

    async def remember(
        self,
        *,
        wing: str,
        hall: str,
        room: str,
        drawer: str,
        content: str,
    ) -> None:
        metadata = {"wing": wing, "hall": hall, "room": room, "drawer": drawer}
        doc_id = f"{wing}:{hall}:{room}:{drawer}"

        def _add() -> None:
            self.collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[metadata],
            )

        await asyncio.to_thread(_add)

    async def search(self, *, query: str, wing: str, k: int) -> list[MemoryHit]:
        def _query() -> dict[str, Any]:
            return self.collection.query(
                query_texts=[query],
                n_results=max(1, k),
                where={"wing": wing},
            )

        raw = await asyncio.to_thread(_query)
        return _parse_chroma_hits(raw)

    async def close(self) -> None:
        return None


def _parse_chroma_hits(raw: dict[str, Any]) -> list[MemoryHit]:
    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0] or [0.0] * len(ids)
    hits: list[MemoryHit] = []
    for i, doc_id in enumerate(ids):
        hits.append(
            MemoryHit(
                id=str(doc_id),
                text=str(docs[i]) if i < len(docs) else "",
                score=1.0 - float(distances[i]) if i < len(distances) else 0.0,
                metadata=dict(metadatas[i]) if i < len(metadatas) else {},
            )
        )
    return hits


class LongTermMemory:
    """Public-facing long-term memory layer used by the orchestrator."""

    def __init__(
        self,
        *,
        collection_name: str,
        chroma_host: str | None = None,
        chroma_port: int | None = None,
        chroma_ssl: bool = False,
        backend: MemPalaceBackend | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._host = chroma_host
        self._port = chroma_port
        self._ssl = chroma_ssl
        self._backend: MemPalaceBackend = backend or self._build_default_backend()

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def _build_default_backend(self) -> MemPalaceBackend:
        if not self._host or not self._port:
            raise RuntimeError("LongTermMemory requires chroma_host+port or an explicit backend")
        import chromadb

        client = chromadb.HttpClient(host=self._host, port=self._port, ssl=self._ssl)
        collection = client.get_or_create_collection(name=self._collection_name)
        # Chroma's real `Collection.add/query` signatures accept more kwargs than
        # we use; cast to our narrower protocol for type-checking purposes.
        return _ChromaBackend(collection=collection)  # type: ignore[arg-type]

    async def remember(self, *, user_id: str, session_id: str, msg_id: str, content: str) -> None:
        """Store `content` verbatim in wing=user_id."""
        await self._backend.remember(
            wing=user_id,
            hall="conversations",
            room=session_id,
            drawer=msg_id,
            content=content,
        )
        logger.info(
            "long_term.remembered",
            user_id=user_id,
            session_id=session_id,
            msg_id=msg_id,
            bytes=len(content),
        )

    async def search(self, *, query: str, user_id: str, k: int = 5) -> list[MemoryHit]:
        if k <= 0 or not query.strip():
            return []
        hits = await self._backend.search(query=query, wing=user_id, k=k)
        logger.info(
            "long_term.search",
            user_id=user_id,
            k=k,
            hits=len(hits),
        )
        return hits

    async def close(self) -> None:
        await self._backend.close()


__all__ = [
    "LongTermMemory",
    "MemPalaceBackend",
    "MemoryHit",
]
