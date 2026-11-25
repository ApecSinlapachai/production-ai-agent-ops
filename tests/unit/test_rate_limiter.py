"""Unit tests for IP-hashed sliding-window rate limiter and proxy-safe 429 behavior."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabasePool
from app.main import create_app
from app.services.rate_limiter import SlidingWindowRateLimiter, extract_client_ip, hash_client_ip
from app.services.repository import AgentRepository


def test_extract_first_forwarded_ip_and_sha256_hash() -> None:
    """First hop of X-Forwarded-For is extracted and hashed irreversibly with SHA-256."""
    fake_req = SimpleNamespace(
        headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    raw_ip = extract_client_ip(fake_req)  # type: ignore[arg-type]
    assert raw_ip == "203.0.113.10"

    digest = hash_client_ip(raw_ip)
    assert len(digest) == 64
    assert digest != raw_ip


def test_sliding_window_rate_limiter_per_minute_and_recovery() -> None:
    """Per-minute cap blocks with positive Retry-After and resets once 60s elapse."""
    now = [1000.0]
    limiter = SlidingWindowRateLimiter(per_minute=2, per_day=10, clock=lambda: now[0])
    ip_hash = hash_client_ip("198.51.100.7")

    assert limiter.check_and_record(ip_hash) == (True, 0)
    assert limiter.check_and_record(ip_hash) == (True, 0)

    allowed, retry_after = limiter.check_and_record(ip_hash)
    assert allowed is False
    assert 1 <= retry_after <= 60

    now[0] += 61.0
    assert limiter.check_and_record(ip_hash) == (True, 0)


def test_sliding_window_rate_limiter_per_day_limit() -> None:
    """Per-day cap rejects excess requests even across separate minutes."""
    now = [1000.0]
    limiter = SlidingWindowRateLimiter(per_minute=10, per_day=3, clock=lambda: now[0])
    ip_hash = hash_client_ip("198.51.100.8")

    for _ in range(3):
        assert limiter.check_and_record(ip_hash) == (True, 0)
        now[0] += 120.0

    allowed, retry_after = limiter.check_and_record(ip_hash)
    assert allowed is False
    assert retry_after >= 1


def test_api_429_returns_retry_after_while_health_remains_exempt(monkeypatch) -> None:
    """Protected routes return 429 with Retry-After, while /health stays 200."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(DatabasePool, "check_health", lambda self: True)
    monkeypatch.setattr(AgentRepository, "list_runs", lambda self, **kwargs: [])

    settings = Settings(
        _env_file=None,
        auth_mode="demo_sandbox",
        rate_limit_per_min=2,
        rate_limit_per_day=10,
    )
    app = create_app(settings=settings)

    headers = {"X-Forwarded-For": "203.0.113.55, 10.0.0.2"}
    with TestClient(app) as client:
        assert client.get("/api/v1/runs", headers=headers).status_code == 200
        assert client.get("/api/v1/runs", headers=headers).status_code == 200

        blocked = client.get("/api/v1/runs", headers=headers)
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1

        # /health must remain available for Render/Vercel warm-up pings
        health = client.get("/health", headers=headers)
        assert health.status_code == 200
