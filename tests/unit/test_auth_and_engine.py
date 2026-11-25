"""Unit tests for AUTH_MODE enforcement and LangGraph intent/transition guards."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabasePool
from app.main import create_app
from app.schemas.enums import AgentState, RiskLevel, RoutingTier, TransitionActor
from app.services.langgraph_engine import _classify_intent
from app.services.repository import AgentRepository, InvalidTransitionError


def test_token_auth_mode_blocks_unauthenticated_and_wrong_token(monkeypatch) -> None:
    """AUTH_MODE=token rejects missing or invalid Bearer tokens with 401."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(AgentRepository, "list_runs", lambda self, **kwargs: [])

    settings = Settings(_env_file=None, auth_mode="token", admin_api_token="secret-token")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        assert client.get("/api/v1/runs").status_code == 401
        assert (
            client.get("/api/v1/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )
        ok_resp = client.get("/api/v1/runs", headers={"Authorization": "Bearer secret-token"})
        assert ok_resp.status_code == 200
        assert ok_resp.json() == []


def test_demo_sandbox_auth_mode_allows_unauthenticated_access(monkeypatch) -> None:
    """AUTH_MODE=demo_sandbox allows public demo requests without Bearer tokens."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(AgentRepository, "list_approvals", lambda self, **kwargs: [])

    settings = Settings(_env_file=None, auth_mode="demo_sandbox")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        resp = client.get("/api/v1/approvals")
        assert resp.status_code == 200
        assert resp.json() == []


def test_intent_classifier_routes_fast_vs_complex_tiers() -> None:
    """Low-risk status inquiries route to FAST; refunds and cancellations route to COMPLEX."""
    intent_fast, tier_fast, conf_fast, risk_fast = _classify_intent(
        "Check shipping status for ORD-2026-1001"
    )
    assert intent_fast == "order_status_inquiry"
    assert tier_fast == RoutingTier.FAST
    assert conf_fast >= 0.90
    assert risk_fast == RiskLevel.LOW

    intent_refund, tier_refund, conf_refund, risk_refund = _classify_intent(
        "ขอคืนเงิน 4,500 บาท สำหรับคำสั่งซื้อ ORD-2026-5501"
    )
    assert intent_refund == "refund_request"
    assert tier_refund == RoutingTier.COMPLEX
    assert conf_refund >= 0.85
    assert risk_refund == RiskLevel.HIGH


def test_repository_rejects_disallowed_state_transition() -> None:
    """AgentRepository raises InvalidTransitionError before touching PostgreSQL."""
    repo = AgentRepository(MagicMock(spec=DatabasePool))
    with pytest.raises(InvalidTransitionError):
        repo.record_transition(
            run_id=uuid4(),
            from_state=AgentState.RECEIVED,
            to_state=AgentState.COMPLETED,
            actor=TransitionActor.SYSTEM,
        )
