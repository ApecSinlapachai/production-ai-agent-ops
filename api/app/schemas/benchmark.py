"""Pydantic v2 schemas for Tiered Model Routing cost & accuracy benchmarks."""

from pydantic import BaseModel, Field


class TierBenchmarkMetrics(BaseModel):
    """Metrics for a single benchmark strategy or routing tier."""

    strategy_name: str
    total_cases: int = Field(..., ge=0)
    accuracy_rate: float = Field(..., ge=0.0, le=1.0)
    avg_latency_ms: float = Field(..., ge=0.0)
    total_cost_usd: float = Field(..., ge=0.0)
    estimated_cost_per_1k_runs_usd: float = Field(..., ge=0.0)


class BenchmarkSummaryResponse(BaseModel):
    """Comparison summary between Always-Frontier and Tiered Routing."""

    baseline: TierBenchmarkMetrics
    tiered: TierBenchmarkMetrics
    cost_reduction_pct: float
    pii_leak_rate: float = Field(..., ge=0.0, le=1.0)
    hitl_enforcement_rate: float = Field(..., ge=0.0, le=1.0)
    live_runs_recorded: int = Field(default=0, ge=0)
