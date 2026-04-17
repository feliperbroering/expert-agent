"""Tests for `expert ask`.

The event/field names here MUST stay in lockstep with the server in
`backend/app/routes/ask.py` (event types `token`, `citation`, `done`,
`error`, with payload fields `text`, `source_uri`, `snippet`, `detail`).
"""

from __future__ import annotations

import json

import httpx
import respx
from expert.main import app
from typer.testing import CliRunner


def _sse_body(events: list[tuple[str, dict[str, object]]]) -> bytes:
    """Encode `(event, data_dict)` tuples into an SSE byte stream."""
    chunks: list[str] = []
    for event, data in events:
        chunks.append(f"event: {event}\ndata: {json.dumps(data)}\n\n")
    return "".join(chunks).encode("utf-8")


@respx.mock
def test_ask_streams_tokens_and_renders_final_markdown() -> None:
    body = _sse_body(
        [
            ("token", {"type": "token", "text": "Hello ", "request_id": "r1"}),
            ("token", {"type": "token", "text": "world!", "request_id": "r1"}),
            (
                "citation",
                {
                    "type": "citation",
                    "request_id": "r1",
                    "source_uri": "gs://bucket/docs/source-a.md",
                    "start_index": 0,
                    "end_index": 12,
                    "snippet": "Example snippet from source A.",
                },
            ),
            (
                "done",
                {
                    "type": "done",
                    "request_id": "r1",
                    "finish_reason": "STOP",
                    "usage": {
                        "input_tokens": 123,
                        "output_tokens": 45,
                        "cached_tokens": 100,
                    },
                    "citations": [],
                },
            ),
        ]
    )
    route = respx.post("https://agent.example.com/ask").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream"},
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ask",
            "What is up?",
            "--session",
            "s-1",
            "--endpoint",
            "https://agent.example.com",
            "--api-key",
            "secret",
        ],
    )

    assert result.exit_code == 0, result.output
    assert route.called
    assert "Hello world!" in result.output
    assert "source-a.md" in result.output
    assert "in=123" in result.output
    assert "out=45" in result.output
    assert "cached=100" in result.output


@respx.mock
def test_ask_non_stream_renders_text_from_json() -> None:
    route = respx.post("https://agent.example.com/ask").mock(
        return_value=httpx.Response(
            200,
            json={
                "text": "**Hello** world!",
                "citations": [
                    {
                        "source_uri": "gs://bucket/docs/b.md",
                        "start_index": 0,
                        "end_index": 5,
                        "snippet": "Bravo source snippet.",
                    }
                ],
                "usage": {"input_tokens": 7, "output_tokens": 3, "cached_tokens": 0},
                "request_id": "req-1",
            },
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ask",
            "hi",
            "--session",
            "s-oneshot",
            "--endpoint",
            "https://agent.example.com",
            "--api-key",
            "secret",
            "--no-stream",
        ],
    )

    assert result.exit_code == 0, result.output
    assert route.called
    assert "Hello" in result.output
    assert "world!" in result.output
    assert "gs://bucket/docs/b.md" in result.output
    assert "in=7" in result.output
    assert "out=3" in result.output


@respx.mock
def test_ask_surfaces_server_error_detail() -> None:
    body = _sse_body(
        [
            ("token", {"type": "token", "text": "partial ", "request_id": "r2"}),
            ("error", {"type": "error", "request_id": "r2", "detail": "LLM blew up"}),
        ]
    )
    respx.post("https://agent.example.com/ask").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream"},
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ask",
            "trigger err",
            "--session",
            "s-err",
            "--endpoint",
            "https://agent.example.com",
            "--api-key",
            "secret",
        ],
    )
    assert result.exit_code == 2
    assert "LLM blew up" in result.output


@respx.mock
def test_ask_handles_auth_failure() -> None:
    respx.post("https://agent.example.com/ask").mock(
        return_value=httpx.Response(401, json={"detail": "unauthorized"}),
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ask",
            "hi",
            "--session",
            "s-2",
            "--endpoint",
            "https://agent.example.com",
            "--api-key",
            "bad",
        ],
    )
    assert result.exit_code == 3
    assert "authentication failed" in result.output.lower()


@respx.mock
def test_ask_handles_connection_error() -> None:
    respx.post("https://agent.example.com/ask").mock(
        side_effect=httpx.ConnectError("unreachable"),
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ask",
            "hi",
            "--session",
            "s-3",
            "--endpoint",
            "https://agent.example.com",
            "--api-key",
            "x",
        ],
    )
    assert result.exit_code == 2
    assert "could not connect" in result.output.lower()
