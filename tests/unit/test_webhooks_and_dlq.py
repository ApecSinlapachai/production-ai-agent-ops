"""Unit tests for /webhooks/n8n secret guard and /api/v1/dlq auth protection."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabasePool
from app.main import create_app
from app.services.repository import AgentRepository


def test_n8n_webhook_always_requires_secret_even_in_demo_sandbox(monkeypatch) -> None:
    """/webhooks/n8n must reject missing or wrong X-Webhook-Secret in demo_sandbox mode."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)

    settings = Settings(
        _env_file=None,
        auth_mode="demo_sandbox",
        n8n_webhook_secret="expected-n8n-secret",
    )
    app = create_app(settings=settings)

    payload = {"message": "Check order status ORD-2026-1001", "event_id": "EVT-001"}
    with TestClient(app) as client:
        missing = client.post("/webhooks/n8n", json=payload)
        assert missing.status_code == 401

        wrong = client.post(
            "/webhooks/n8n",
            json=payload,
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        assert wrong.status_code == 401


def test_dlq_endpoints_require_bearer_token_in_token_mode(monkeypatch) -> None:
    """/api/v1/dlq enforces Bearer auth when AUTH_MODE=token."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(AgentRepository, "list_dlq_jobs", lambda self, **kwargs: [])
    _ = MagicMock()

    settings = Settings(
        _env_file=None,
        auth_mode="token",
        admin_api_token="admin-secret-token",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        assert client.get("/api/v1/dlq").status_code == 401
        ok = client.get("/api/v1/dlq", headers={"Authorization": "Bearer admin-secret-token"})
        assert ok.status_code == 200
        assert ok.json() == []
