"""Read-only benchmark scorecard endpoint (`/api/v1/benchmark`)."""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_api_auth

router = APIRouter(
    prefix="/api/v1/benchmark",
    tags=["benchmark"],
    dependencies=[Depends(require_api_auth)],
)

EVAL_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "eval" / "run_benchmark.py"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmark_snapshot.json"


@lru_cache(maxsize=1)
def _load_benchmark_report() -> dict[str, Any]:
    if EVAL_SCRIPT_PATH.is_file():
        spec = importlib.util.spec_from_file_location("eval_run_benchmark", EVAL_SCRIPT_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load module spec from {EVAL_SCRIPT_PATH}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run_benchmark()

    if SNAPSHOT_PATH.is_file():
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        f"Benchmark runner not found at {EVAL_SCRIPT_PATH} and snapshot missing at {SNAPSHOT_PATH}"
    )


@router.get("")
def get_benchmark_scorecard() -> dict[str, Any]:
    """Return the verified Always-Frontier vs Tiered-Routing cost and safety scorecard."""
    try:
        return _load_benchmark_report()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
