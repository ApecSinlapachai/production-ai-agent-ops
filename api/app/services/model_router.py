"""Tiered Gemini model router with 429/5xx fallback chains and deterministic offline replay."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google import genai

from app.config import Settings
from app.schemas.enums import RiskLevel, RoutingTier

logger = logging.getLogger(__name__)

# Indicative USD per 1M tokens for cost accounting (FAST vs COMPLEX tiers)
TIER_PRICING_PER_1M: dict[RoutingTier, tuple[float, float]] = {
    RoutingTier.FAST: (0.10, 0.40),
    RoutingTier.COMPLEX: (0.60, 2.40),
    RoutingTier.RULE_FALLBACK: (0.0, 0.0),
}

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_RETRYABLE_MARKERS: tuple[str, ...] = (
    "429",
    "resource_exhausted",
    "unavailable",
    "deadline_exceeded",
    "timeout",
)


def estimate_tokens(text: str) -> int:
    """Estimate token count deterministically without external tokenizer dependencies."""
    return max(12, int(len(text) / 3.5))


def estimate_cost(tier: RoutingTier, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a single LLM call based on routing tier token pricing."""
    in_price, out_price = TIER_PRICING_PER_1M[tier]
    cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    return round(cost, 6)


@dataclass(slots=True)
class ModelCallResult:
    """Structured outcome and usage telemetry from a routed model call."""

    text: str
    model_used: str
    routing_tier: RoutingTier
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    is_fallback: bool
    fallback_reason: str | None = None


class TieredModelRouter:
    """Routes FAST vs COMPLEX steps to Gemini models with automatic 429 fallback."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._client = client

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if not self._settings.gemini_api_key.strip():
            return None
        self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    def _candidate_models(self, tier: RoutingTier) -> list[str]:
        if tier == RoutingTier.RULE_FALLBACK:
            return []
        if tier == RoutingTier.FAST:
            raw = [self._settings.gemini_fast_model, *self._settings.fallback_model_list]
        else:
            raw = [
                self._settings.gemini_complex_model,
                self._settings.gemini_fast_model,
                *self._settings.fallback_model_list,
            ]
        seen: set[str] = set()
        ordered: list[str] = []
        for model in raw:
            if model and model not in seen:
                seen.add(model)
                ordered.append(model)
        return ordered

    @staticmethod
    def _is_fallback_trigger(exc: Exception) -> bool:
        status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if isinstance(status_code, int) and status_code in _RETRYABLE_STATUS_CODES:
            return True
        message = str(exc).lower()
        return any(marker in message for marker in _RETRYABLE_MARKERS)

    def generate_text(
        self,
        *,
        step_name: str,
        requested_tier: RoutingTier,
        prompt: str,
        system_instruction: str,
        fallback_fn: Callable[[], str],
    ) -> ModelCallResult:
        """Execute a tiered model call, falling back cleanly on 429/errors or offline mode."""
        started = time.perf_counter()
        candidates = self._candidate_models(requested_tier)
        client = self._get_client()

        if client is None or not candidates:
            text = fallback_fn()
            in_tok = estimate_tokens(prompt) + 40
            out_tok = estimate_tokens(text)
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            return ModelCallResult(
                text=text,
                model_used=candidates[0] if candidates else "rule-fallback",
                routing_tier=requested_tier,
                input_tokens=in_tok,
                output_tokens=out_tok,
                estimated_cost_usd=estimate_cost(requested_tier, in_tok, out_tok),
                latency_ms=latency_ms,
                is_fallback=True,
                fallback_reason="no_api_key" if client is None else "rule_tier",
            )

        for idx, model_name in enumerate(candidates):
            effective_tier = requested_tier if idx == 0 else RoutingTier.FAST
            try:
                interaction = client.interactions.create(
                    model=model_name,
                    input=prompt,
                    system_instruction=system_instruction,
                    store=False,
                )
                text = (getattr(interaction, "output_text", None) or "").strip()
                if not text:
                    raise ValueError(f"Empty model output from {model_name}")

                usage = getattr(interaction, "usage", None)
                raw_in = getattr(usage, "total_input_tokens", None) if usage else None
                raw_out = getattr(usage, "total_output_tokens", None) if usage else None
                in_tok = int(raw_in) if isinstance(raw_in, int) and raw_in >= 0 else (
                    estimate_tokens(prompt) + 40
                )
                out_tok = int(raw_out) if isinstance(raw_out, int) and raw_out >= 0 else (
                    estimate_tokens(text)
                )
                latency_ms = max(1, int((time.perf_counter() - started) * 1000))
                return ModelCallResult(
                    text=text,
                    model_used=model_name,
                    routing_tier=effective_tier,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    estimated_cost_usd=estimate_cost(effective_tier, in_tok, out_tok),
                    latency_ms=latency_ms,
                    is_fallback=idx > 0,
                    fallback_reason="model_fallback" if idx > 0 else None,
                )
            except Exception as exc:
                reason = "retryable" if self._is_fallback_trigger(exc) else "sdk_error"
                logger.warning(
                    "Model step=%s candidate=%s failed (%s): %s",
                    step_name,
                    model_name,
                    reason,
                    exc,
                )

        text = fallback_fn()
        in_tok = estimate_tokens(prompt) + 40
        out_tok = estimate_tokens(text)
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return ModelCallResult(
            text=text,
            model_used="rule-fallback",
            routing_tier=RoutingTier.RULE_FALLBACK,
            input_tokens=in_tok,
            output_tokens=out_tok,
            estimated_cost_usd=0.0,
            latency_ms=latency_ms,
            is_fallback=True,
            fallback_reason="all_models_exhausted",
        )

    def classify_intent(
        self,
        redacted_message: str,
        fallback_classifier: Callable[[str], tuple[str, RoutingTier, float, RiskLevel]],
    ) -> tuple[str, RoutingTier, float, RiskLevel, ModelCallResult]:
        """Classify redacted request intent on the FAST tier with structured fallback."""
        system_instruction = (
            "You are an operations triage classifier. Reply with a single JSON object only "
            '(no markdown): {"intent": str, "routing_tier": "FAST"|"COMPLEX", '
            '"confidence": float_0_to_1, "risk_level": "LOW"|"MEDIUM"|"HIGH"}. '
            "Use COMPLEX + HIGH for refunds, cancellations, billing credits, or disputes."
        )

        def _offline_json() -> str:
            intent, tier, confidence, risk_level = fallback_classifier(redacted_message)
            return json.dumps(
                {
                    "intent": intent,
                    "routing_tier": tier.value,
                    "confidence": confidence,
                    "risk_level": risk_level.value,
                }
            )

        call_result = self.generate_text(
            step_name="route_intent",
            requested_tier=RoutingTier.FAST,
            prompt=f"Classify this PII-redacted customer operations message:\n{redacted_message}",
            system_instruction=system_instruction,
            fallback_fn=_offline_json,
        )

        parsed = self._parse_classification_json(call_result.text)
        if parsed is not None:
            return (*parsed, call_result)

        intent, tier, confidence, risk_level = fallback_classifier(redacted_message)
        call_result.is_fallback = True
        call_result.fallback_reason = call_result.fallback_reason or "parse_fallback"
        return intent, tier, confidence, risk_level, call_result

    @staticmethod
    def _parse_classification_json(
        raw_text: str,
    ) -> tuple[str, RoutingTier, float, RiskLevel] | None:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        try:
            payload = json.loads(cleaned)
            if not isinstance(payload, dict):
                return None
            intent = str(payload["intent"]).strip()
            if not intent:
                return None
            tier = RoutingTier(str(payload["routing_tier"]).strip().upper())
            if tier == RoutingTier.RULE_FALLBACK:
                tier = RoutingTier.FAST
            risk_level = RiskLevel(str(payload["risk_level"]).strip().upper())
            confidence = max(0.0, min(1.0, float(payload["confidence"])))
            return intent, tier, confidence, risk_level
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def generate_draft(
        self,
        *,
        intent: str,
        tier: RoutingTier,
        redacted_message: str,
        customer_ref: str | None,
        context: dict[str, Any],
        fallback_draft: str,
    ) -> tuple[str, ModelCallResult]:
        """Generate an operations draft response using only PII-redacted inputs."""
        system_instruction = (
            "You are an enterprise operations assistant. Write a concise, polite, accurate "
            "response using only the PII-redacted message and context. Never invent customer PII."
        )
        prompt = (
            f"Intent: {intent}\n"
            f"Customer Ref: {customer_ref or 'CUST-ANONYMOUS'}\n"
            f"Context: {json.dumps(context, ensure_ascii=False)}\n"
            f"Redacted Message: {redacted_message}\n"
            "Write the draft customer response in 2-3 sentences."
        )
        call_result = self.generate_text(
            step_name="generate_draft",
            requested_tier=tier,
            prompt=prompt,
            system_instruction=system_instruction,
            fallback_fn=lambda: fallback_draft,
        )
        return call_result.text, call_result
