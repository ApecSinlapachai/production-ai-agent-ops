"""Unit tests for TieredModelRouter fallback chains and exportable n8n workflow JSONs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.schemas.enums import RiskLevel, RoutingTier
from app.services.langgraph_engine import _classify_intent
from app.services.model_router import TieredModelRouter

N8N_DIR = Path(__file__).resolve().parents[2] / "n8n"


class _FakeRateLimitError(Exception):
    def __init__(self, code: int = 429, message: str = "429 RESOURCE_EXHAUSTED") -> None:
        super().__init__(message)
        self.code = code


class _FakeInteractions:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(**kwargs)


class _FakeClient:
    def __init__(self, handler) -> None:
        self.interactions = _FakeInteractions(handler)


def test_model_router_offline_mode_uses_deterministic_fallback() -> None:
    """When GEMINI_API_KEY is unset, router uses deterministic fallback and preserves tier."""
    settings = Settings(_env_file=None, gemini_api_key="")
    router = TieredModelRouter(settings)

    intent, tier, confidence, risk, result = router.classify_intent(
        "Check shipping status for ORD-2026-1001",
        _classify_intent,
    )
    assert intent == "order_status_inquiry"
    assert tier == RoutingTier.FAST
    assert confidence >= 0.90
    assert risk == RiskLevel.LOW
    assert result.is_fallback is True
    assert result.fallback_reason == "no_api_key"
    assert result.model_used == settings.gemini_fast_model


def test_model_router_live_client_fast_and_complex_success() -> None:
    """Live client routes FAST and COMPLEX models with store=False and usage telemetry."""
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        gemini_fast_model="gemini-3.5-flash-lite",
        gemini_complex_model="gemini-3.8-flash",
    )

    def _handler(**kwargs):
        return SimpleNamespace(
            output_text="Drafted response for ORD-2026-5501.",
            usage=SimpleNamespace(total_input_tokens=120, total_output_tokens=32),
        )

    client = _FakeClient(_handler)
    router = TieredModelRouter(settings, client=client)

    draft, result = router.generate_draft(
        intent="refund_request",
        tier=RoutingTier.COMPLEX,
        redacted_message="Refund request for ORD-2026-5501",
        customer_ref="CUST-DEMO-03",
        context={"order_ref": "ORD-2026-5501"},
        fallback_draft="fallback draft",
    )
    assert draft == "Drafted response for ORD-2026-5501."
    assert result.model_used == "gemini-3.8-flash"
    assert result.routing_tier == RoutingTier.COMPLEX
    assert result.input_tokens == 120
    assert result.output_tokens == 32
    assert result.is_fallback is False
    assert client.interactions.calls[0]["store"] is False


def test_model_router_falls_back_on_429_resource_exhausted() -> None:
    """429 RESOURCE_EXHAUSTED on primary model transparently falls back to secondary model."""
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        gemini_fast_model="gemini-3.5-flash-lite",
        gemini_complex_model="gemini-3.8-flash",
        gemini_fallback_models="gemini-3.1-flash-lite",
    )

    def _handler(**kwargs):
        if kwargs["model"] == "gemini-3.8-flash":
            raise _FakeRateLimitError(429, "429 RESOURCE_EXHAUSTED")
        return SimpleNamespace(
            output_text="Fallback draft generated safely.",
            usage=SimpleNamespace(total_input_tokens=80, total_output_tokens=20),
        )

    client = _FakeClient(_handler)
    router = TieredModelRouter(settings, client=client)

    result = router.generate_text(
        step_name="generate_draft",
        requested_tier=RoutingTier.COMPLEX,
        prompt="Draft reply",
        system_instruction="Be concise.",
        fallback_fn=lambda: "rule fallback",
    )
    assert result.text == "Fallback draft generated safely."
    assert result.model_used == "gemini-3.5-flash-lite"
    assert result.routing_tier == RoutingTier.FAST
    assert result.is_fallback is True
    assert result.fallback_reason == "model_fallback"


def test_model_router_exhaustion_reaches_rule_fallback() -> None:
    """When all Gemini candidates fail with 429, router falls back to deterministic rule output."""
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        gemini_fast_model="gemini-3.5-flash-lite",
        gemini_complex_model="gemini-3.8-flash",
        gemini_fallback_models="gemini-3.1-flash-lite",
    )

    def _always_429(**kwargs):
        raise _FakeRateLimitError(429, "429 RESOURCE_EXHAUSTED")

    client = _FakeClient(_always_429)
    router = TieredModelRouter(settings, client=client)

    result = router.generate_text(
        step_name="generate_draft",
        requested_tier=RoutingTier.COMPLEX,
        prompt="Draft reply",
        system_instruction="Be concise.",
        fallback_fn=lambda: "deterministic rule draft",
    )
    assert result.text == "deterministic rule draft"
    assert result.model_used == "rule-fallback"
    assert result.routing_tier == RoutingTier.RULE_FALLBACK
    assert result.estimated_cost_usd == 0.0
    assert result.is_fallback is True
    assert result.fallback_reason == "all_models_exhausted"
    assert len(client.interactions.calls) == 3


def test_n8n_workflows_valid_json_and_zero_hardcoded_secrets() -> None:
    """Exportable n8n workflow JSONs parse cleanly and contain no hardcoded secrets."""
    workflow_files = sorted(N8N_DIR.glob("*.json"))
    assert len(workflow_files) == 2

    for wf_path in workflow_files:
        raw_text = wf_path.read_text(encoding="utf-8")
        assert "change-me-" not in raw_text
        data = json.loads(raw_text)
        assert isinstance(data["nodes"], list) and len(data["nodes"]) >= 4
        assert isinstance(data["connections"], dict) and len(data["connections"]) >= 2
