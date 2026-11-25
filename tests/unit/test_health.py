"""Unit tests for `/health` endpoint and CORS headers."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabasePool
from app.main import create_app


def test_health_endpoint_reports_connected_when_db_ok(monkeypatch) -> None:
    """GET /health returns status=ok and connected when DB check succeeds."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(DatabasePool, "check_health", lambda self: True)

    settings = Settings(_env_file=None, auth_mode="demo_sandbox")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "connected",
        "auth_mode": "demo_sandbox",
        "fast_model": "gemini-3.5-flash-lite",
        "complex_model": "gemini-3.8-flash",
    }
    assert "Retry-After" in response.headers.get("access-control-expose-headers", "")


def test_health_endpoint_reports_degraded_when_db_unavailable(monkeypatch) -> None:
    """GET /health returns status=degraded when DB check fails."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(DatabasePool, "check_health", lambda self: False)

    app = create_app(settings=Settings(_env_file=None))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == "degraded"
