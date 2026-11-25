"""Automated evaluation gate tests for PDPA redaction, HITL enforcement, and cost savings."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabasePool
from app.main import create_app

EVAL_SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "run_benchmark.py"


def _run_eval():
    spec = importlib.util.spec_from_file_location("eval_run_benchmark", EVAL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_benchmark()


def test_benchmark_gates_pass_all_safety_and_cost_thresholds() -> None:
    """Benchmark meets 0% PII leak, 100% HITL enforcement, and 50-75% cost reduction."""
    report = _run_eval()
    assert report["total_cases"] >= 20
    assert report["pii_leak_rate"] == 0.0
    assert report["hitl_enforcement_rate"] == 1.0
    assert 50.0 <= report["cost_reduction_pct"] <= 75.0
    assert report["gates_passed"] is True, f"Gate failures: {report['gate_failures']}"


def test_benchmark_endpoint_returns_passing_scorecard(monkeypatch) -> None:
    """GET /api/v1/benchmark serves the verified cost-routing and safety scorecard."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)

    app = create_app(settings=Settings(_env_file=None, auth_mode="demo_sandbox"))
    with TestClient(app) as client:
        resp = client.get("/api/v1/benchmark")
        assert resp.status_code == 200
        body = resp.json()
        assert body["gates_passed"] is True
        assert body["pii_leak_rate"] == 0.0
        assert body["cost_reduction_pct"] >= 50.0
