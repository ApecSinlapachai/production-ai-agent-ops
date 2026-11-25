"""Read-only benchmark scorecard endpoint (`/api/v1/benchmark`)."""

from __future__ import annotations

import importlib.util
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


@lru_cache(maxsize=1)
def _load_benchmark_report() -> dict[str, Any]:
    eval_script = Path(__file__).resolve().parents[3] / "eval" / "run_benchmark.py"
    if not eval_script.is_file():
        raise FileNotFoundError(f"Benchmark runner not found at {eval_script}")

    spec = importlib.util.spec_from_file_location("eval_run_benchmark", eval_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec from {eval_script}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_benchmark()


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
