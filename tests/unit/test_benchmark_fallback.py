"""Unit tests for container-safe benchmark snapshot fallback."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabasePool
from app.main import create_app
from app.routers import benchmark as benchmark_router


def test_benchmark_snapshot_file_is_valid_and_passing() -> None:
    """Static benchmark snapshot exists inside api/app/data and satisfies CI gates."""
    snapshot_path = benchmark_router.SNAPSHOT_PATH
    assert snapshot_path.is_file()

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["gates_passed"] is True
    assert snapshot["pii_leak_rate"] == 0.0
    assert snapshot["hitl_enforcement_rate"] == 1.0
    assert 50.0 <= snapshot["cost_reduction_pct"] <= 75.0
    assert "always_frontier" in snapshot
    assert "tiered_routing" in snapshot


def test_benchmark_falls_back_to_snapshot_when_eval_script_missing(monkeypatch) -> None:
    """When eval/run_benchmark.py is absent (Docker), GET /api/v1/benchmark serves the snapshot."""
    monkeypatch.setattr(DatabasePool, "open", lambda self: None)
    monkeypatch.setattr(DatabasePool, "close", lambda self: None)
    monkeypatch.setattr(
        benchmark_router,
        "EVAL_SCRIPT_PATH",
        Path("/nonexistent/eval/run_benchmark.py"),
    )
    benchmark_router._load_benchmark_report.cache_clear()

    try:
        app = create_app(settings=Settings(_env_file=None, auth_mode="demo_sandbox"))
        with TestClient(app) as client:
            resp = client.get("/api/v1/benchmark")
            assert resp.status_code == 200
            body = resp.json()
            assert body["gates_passed"] is True
            assert body["total_cases"] >= 20
            assert body["cost_reduction_pct"] >= 50.0
    finally:
        benchmark_router._load_benchmark_report.cache_clear()
