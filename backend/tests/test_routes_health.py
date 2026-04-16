"""Smoke tests for the public /health and /ready endpoints."""

from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient


def test_health_returns_agent_metadata() -> None:
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["agent_id"] == "example-expert"
    assert "version" in body
    assert "model" in body


def test_ready_reports_components() -> None:
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 200
    body = resp.json()
    assert "checks" in body
    assert set(body["checks"].keys()) == {"llm", "firestore", "chroma"}


def test_metrics_exposes_prometheus_format() -> None:
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/metrics")

    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
