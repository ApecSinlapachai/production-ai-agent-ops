"""Reproducible evaluation and Always-Frontier vs Tiered-Routing cost benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.schemas.enums import RoutingTier  # noqa: E402
from app.services.langgraph_engine import (  # noqa: E402
    HIGH_IMPACT_INTENTS,
    _build_proposed_action,
    _classify_intent,
)
from app.services.model_router import estimate_cost, estimate_tokens  # noqa: E402
from app.services.pii_redactor import find_leaked_pii, redact_payload  # noqa: E402

DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "benchmark_cases.json"
DEFAULT_THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.json"


def run_benchmark(
    *,
    cases_path: Path = DEFAULT_CASES_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
) -> dict[str, Any]:
    """Run PDPA redaction, HITL policy, routing accuracy, and cost-reduction benchmark."""
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    settings = Settings(_env_file=None)

    total_cases = len(cases)
    if total_cases == 0:
        raise ValueError("Benchmark case file is empty.")

    pii_leaked_cases = 0
    pii_entities_redacted = 0
    hitl_expected_total = 0
    hitl_enforced_total = 0
    intent_correct = 0
    routing_correct = 0
    fast_cases = 0
    complex_cases = 0

    frontier_input_tokens = 0
    frontier_output_tokens = 0
    frontier_cost_usd = 0.0

    tiered_input_tokens = 0
    tiered_output_tokens = 0
    tiered_cost_usd = 0.0

    for case in cases:
        raw_payload = {
            "message": case["message"],
            "customer_ref": case.get("customer_ref"),
        }
        redacted_payload, redaction_summary = redact_payload(raw_payload)
        redacted_message = str(redacted_payload["message"])
        pii_entities_redacted += redaction_summary.total_redacted

        leaks = find_leaked_pii(redacted_message, case.get("raw_pii_values", []))
        if leaks:
            pii_leaked_cases += 1

        intent, tier, confidence, _risk = _classify_intent(redacted_message)
        if intent == case["expected_intent"]:
            intent_correct += 1
        if tier.value == case["expected_routing_tier"]:
            routing_correct += 1

        if tier == RoutingTier.FAST:
            fast_cases += 1
        else:
            complex_cases += 1

        context = {
            "customer_ref": case.get("customer_ref") or "CUST-ANONYMOUS",
            "order_ref": "ORD-BENCHMARK",
        }
        draft_text, proposed_action = _build_proposed_action(
            intent=intent,
            redacted_message=redacted_message,
            customer_ref=case.get("customer_ref"),
            context=context,
        )
        requires_hitl = (
            intent in HIGH_IMPACT_INTENTS
            or confidence < settings.hitl_confidence_threshold
            or bool(proposed_action.get("requires_human_approval"))
        )
        if case["expected_requires_hitl"]:
            hitl_expected_total += 1
            if requires_hitl:
                hitl_enforced_total += 1

        # Token footprint per run: step 1 (route_intent) + step 2 (generate_draft)
        route_in = estimate_tokens(redacted_message) + 40
        route_out = 24
        draft_in = estimate_tokens(redacted_message) + 90
        draft_out = estimate_tokens(draft_text) + 30

        run_in_tokens = route_in + draft_in
        run_out_tokens = route_out + draft_out

        frontier_input_tokens += run_in_tokens
        frontier_output_tokens += run_out_tokens
        frontier_cost_usd += estimate_cost(RoutingTier.COMPLEX, route_in, route_out)
        frontier_cost_usd += estimate_cost(RoutingTier.COMPLEX, draft_in, draft_out)

        tiered_input_tokens += run_in_tokens
        tiered_output_tokens += run_out_tokens
        tiered_cost_usd += estimate_cost(RoutingTier.FAST, route_in, route_out)
        tiered_cost_usd += estimate_cost(tier, draft_in, draft_out)

    pii_leak_rate = round(pii_leaked_cases / total_cases, 4)
    hitl_enforcement_rate = (
        round(hitl_enforced_total / hitl_expected_total, 4) if hitl_expected_total else 1.0
    )
    intent_accuracy = round(intent_correct / total_cases, 4)
    routing_accuracy = round(routing_correct / total_cases, 4)

    frontier_per_1000 = round((frontier_cost_usd / total_cases) * 1000, 4)
    tiered_per_1000 = round((tiered_cost_usd / total_cases) * 1000, 4)
    cost_reduction_pct = (
        round(((frontier_cost_usd - tiered_cost_usd) / frontier_cost_usd) * 100, 2)
        if frontier_cost_usd > 0
        else 0.0
    )

    gate_failures: list[str] = []
    if pii_leak_rate > thresholds["max_pii_leak_rate"]:
        gate_failures.append(
            f"pii_leak_rate={pii_leak_rate} exceeds max {thresholds['max_pii_leak_rate']}"
        )
    if hitl_enforcement_rate < thresholds["min_hitl_enforcement_rate"]:
        gate_failures.append(
            f"hitl_enforcement_rate={hitl_enforcement_rate} below min "
            f"{thresholds['min_hitl_enforcement_rate']}"
        )
    if intent_accuracy < thresholds["min_intent_accuracy"]:
        gate_failures.append(
            f"intent_accuracy={intent_accuracy} below min {thresholds['min_intent_accuracy']}"
        )
    if routing_accuracy < thresholds["min_routing_accuracy"]:
        gate_failures.append(
            f"routing_accuracy={routing_accuracy} below min {thresholds['min_routing_accuracy']}"
        )
    if not (
        thresholds["min_cost_reduction_pct"]
        <= cost_reduction_pct
        <= thresholds["max_cost_reduction_pct"]
    ):
        gate_failures.append(
            f"cost_reduction_pct={cost_reduction_pct}% outside "
            f"[{thresholds['min_cost_reduction_pct']}%, {thresholds['max_cost_reduction_pct']}%]"
        )

    return {
        "total_cases": total_cases,
        "fast_cases": fast_cases,
        "complex_cases": complex_cases,
        "pii_entities_redacted": pii_entities_redacted,
        "pii_leak_rate": pii_leak_rate,
        "hitl_enforcement_rate": hitl_enforcement_rate,
        "intent_accuracy": intent_accuracy,
        "routing_accuracy": routing_accuracy,
        "always_frontier": {
            "model": settings.gemini_complex_model,
            "total_input_tokens": frontier_input_tokens,
            "total_output_tokens": frontier_output_tokens,
            "total_cost_usd": round(frontier_cost_usd, 6),
            "cost_per_1000_runs_usd": frontier_per_1000,
        },
        "tiered_routing": {
            "fast_model": settings.gemini_fast_model,
            "complex_model": settings.gemini_complex_model,
            "total_input_tokens": tiered_input_tokens,
            "total_output_tokens": tiered_output_tokens,
            "total_cost_usd": round(tiered_cost_usd, 6),
            "cost_per_1000_runs_usd": tiered_per_1000,
        },
        "cost_reduction_pct": cost_reduction_pct,
        "thresholds": thresholds,
        "gates_passed": len(gate_failures) == 0,
        "gate_failures": gate_failures,
    }


def format_markdown_report(report: dict[str, Any]) -> str:
    """Format benchmark results into a concise Markdown scorecard table."""
    frontier = report["always_frontier"]
    tiered = report["tiered_routing"]
    lines = [
        "### Tiered Model Routing & Safety Benchmark",
        "",
        f"- **Cases Evaluated:** {report['total_cases']} "
        f"({report['fast_cases']} FAST / {report['complex_cases']} COMPLEX)",
        f"- **PDPA PII Redacted:** {report['pii_entities_redacted']} entities "
        f"(Leak Rate: `{report['pii_leak_rate']:.2f}`)",
        f"- **HITL Policy Enforcement:** `{report['hitl_enforcement_rate']:.2f}` | "
        f"**Intent Accuracy:** `{report['intent_accuracy']:.2%}` | "
        f"**Routing Accuracy:** `{report['routing_accuracy']:.2%}`",
        "",
        "| Strategy | Models | Est. Cost / 1,000 Runs (USD) | Cost Reduction |",
        "|---|---|---:|---:|",
        f"| Always-Frontier Baseline | `{frontier['model']}` | "
        f"`${frontier['cost_per_1000_runs_usd']:.4f}` | `0.00%` |",
        f"| Tiered Model Routing | `{tiered['fast_model']}` + `{tiered['complex_model']}` | "
        f"`${tiered['cost_per_1000_runs_usd']:.4f}` | **`{report['cost_reduction_pct']:.2f}%`** |",
        "",
        f"- **CI Gates Passed:** `{report['gates_passed']}`",
    ]
    if report["gate_failures"]:
        lines.append(f"- **Failures:** {'; '.join(report['gate_failures'])}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Tiered Model Routing & Safety Benchmark.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    report = run_benchmark()
    print(format_markdown_report(report))
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return 0 if report["gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
