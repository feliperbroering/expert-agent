"""structlog configuration producing JSON-line logs for Cloud Logging.

Cloud Logging auto-parses JSON on stdout; the fields below surface in the
`jsonPayload` of each log entry. `severity` (added by `add_log_level`) is
mapped by the Cloud Logging agent.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from typing import Any

import structlog

REQUEST_FIELDS: tuple[str, ...] = (
    "request_id",
    "user_id",
    "session_id",
    "route",
    "latency_ms",
    "tokens_input",
    "tokens_output",
    "tokens_cached",
    "cost_usd",
    "cache_hit",
)


def _rename_level_to_severity(
    _logger: logging.Logger, _name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Cloud Logging expects `severity`; structlog emits `level` by default."""
    level = event_dict.pop("level", None)
    if level is not None:
        event_dict["severity"] = level.upper()
    return event_dict


def _ensure_request_fields(
    _logger: logging.Logger, _name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Ensure the canonical request-scoped fields are present (possibly null).

    Having a stable schema makes Cloud Logging filters predictable.
    """
    for field in REQUEST_FIELDS:
        event_dict.setdefault(field, None)
    return event_dict


def configure_logging(level: str = "INFO", *, extra_processors: Iterable[Any] = ()) -> None:
    """Configure structlog + stdlib logging to emit JSON on stdout."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _rename_level_to_severity,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _ensure_request_fields,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        *extra_processors,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Helper to grab a pre-configured logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


__all__ = ["REQUEST_FIELDS", "configure_logging", "get_logger"]
