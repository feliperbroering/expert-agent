"""Background task that extends the Gemini Context Cache TTL before expiry."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import structlog
from prometheus_client import Counter

from ..llm.protocol import LLMClient
from .manager import CacheManager

logger = structlog.get_logger(__name__)

CACHE_REFRESH_TOTAL = Counter(
    "expert_agent_cache_refresh_total",
    "Context cache refresh attempts, labelled by outcome.",
    labelnames=("status",),
)


class CacheRefresher:
    """Async loop that periodically calls `llm.update_cache_ttl`."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        cache_manager: CacheManager,
        ttl_seconds: int,
        refresh_before_expiry_seconds: int,
    ) -> None:
        if refresh_before_expiry_seconds >= ttl_seconds:
            raise ValueError("refresh_before_expiry_seconds must be smaller than ttl_seconds")
        self._llm = llm
        self._cache_manager = cache_manager
        self._ttl_seconds = ttl_seconds
        self._interval = max(30, ttl_seconds - refresh_before_expiry_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def interval_seconds(self) -> int:
        return self._interval

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="cache-refresher")
        logger.info("cache.refresher.started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("cache.refresher.stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
                return
            except TimeoutError:
                await self._tick()

    async def _tick(self) -> None:
        cache = self._cache_manager.current
        if cache is None:
            CACHE_REFRESH_TOTAL.labels(status="expired").inc()
            logger.info("cache.refresher.no_current_cache")
            return
        try:
            await self._llm.update_cache_ttl(cache, self._ttl_seconds)
            CACHE_REFRESH_TOTAL.labels(status="ok").inc()
            logger.info("cache.refresher.ok", cache_name=cache.name)
        except Exception as exc:
            CACHE_REFRESH_TOTAL.labels(status="error").inc()
            logger.warning(
                "cache.refresher.error",
                cache_name=cache.name,
                error=str(exc),
            )


__all__ = ["CACHE_REFRESH_TOTAL", "CacheRefresher"]
