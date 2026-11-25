"use client";

import { BarChart3, CheckCircle2, RefreshCw, ShieldCheck, TrendingDown } from "lucide-react";
import type { BenchmarkReport } from "@/lib/types";

interface BenchmarkScorecardProps {
  report: BenchmarkReport | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export function BenchmarkScorecard({
  report,
  loading,
  error,
  onRefresh,
}: BenchmarkScorecardProps) {
  if (loading && !report) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-6 text-xs text-slate-400">
        Loading Tiered Model Routing &amp; Safety Benchmark...
      </div>
    );
  }

  if (error && !report) {
    return (
      <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-200">
        {error}
      </div>
    );
  }

  if (!report) return null;

  const frontierCost = report.always_frontier.cost_per_1000_runs_usd;
  const tieredCost = report.tiered_routing.cost_per_1000_runs_usd;
  const tieredWidthPct = frontierCost > 0 ? Math.max(8, (tieredCost / frontierCost) * 100) : 40;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/75 p-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <BarChart3 className="h-4 w-4 text-emerald-400" />
            Tiered Model Routing &amp; Safety Benchmark ({report.total_cases} TH/EN Cases)
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Live scorecard served from <code className="text-slate-300">GET /api/v1/benchmark</code>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-xs font-semibold ${
              report.gates_passed
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                : "border-rose-500/50 bg-rose-500/15 text-rose-300"
            }`}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            CI Gates: {report.gates_passed ? "PASSED" : "FAILED"}
          </span>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-emerald-500/30 bg-slate-900/75 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Cost Reduction</span>
            <TrendingDown className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-emerald-300">
            {report.cost_reduction_pct.toFixed(2)}%
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            Target gate: {report.thresholds.min_cost_reduction_pct}% –{" "}
            {report.thresholds.max_cost_reduction_pct}%
          </div>
        </div>

        <div className="rounded-xl border border-cyan-500/30 bg-slate-900/75 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>PDPA PII Leak Rate</span>
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-cyan-300">
            {report.pii_leak_rate.toFixed(2)}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            {report.pii_entities_redacted} entities masked across {report.total_cases} cases
          </div>
        </div>

        <div className="rounded-xl border border-amber-500/30 bg-slate-900/75 p-4">
          <div className="text-xs text-slate-400">HITL Policy Enforcement</div>
          <div className="mt-2 font-mono text-2xl font-bold text-amber-300">
            {(report.hitl_enforcement_rate * 100).toFixed(0)}%
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            All high-impact actions gated at AWAITING_APPROVAL
          </div>
        </div>

        <div className="rounded-xl border border-indigo-500/30 bg-slate-900/75 p-4">
          <div className="text-xs text-slate-400">Intent &amp; Routing Accuracy</div>
          <div className="mt-2 font-mono text-2xl font-bold text-indigo-300">
            {(report.intent_accuracy * 100).toFixed(0)}% /{" "}
            {(report.routing_accuracy * 100).toFixed(0)}%
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            Split: {report.fast_cases} FAST / {report.complex_cases} COMPLEX
          </div>
        </div>
      </div>

      {/* Cost Comparison Bar Visualization */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/75 p-5">
        <h3 className="mb-4 text-sm font-semibold text-slate-100">
          Estimated Cost per 1,000 Agent Runs (USD)
        </h3>

        <div className="space-y-4">
          <div>
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="font-medium text-slate-200">
                Always-Frontier Baseline (
                <code className="text-purple-300">{report.always_frontier.model}</code>)
              </span>
              <span className="font-mono font-semibold text-slate-200">
                ${frontierCost.toFixed(4)} / 1k runs
              </span>
            </div>
            <div className="h-4 w-full overflow-hidden rounded-full bg-slate-800">
              <div className="h-full w-full rounded-full bg-gradient-to-r from-purple-500 to-rose-500" />
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="font-medium text-slate-200">
                Tiered Model Routing (
                <code className="text-emerald-300">{report.tiered_routing.fast_model}</code> +{" "}
                <code className="text-purple-300">{report.tiered_routing.complex_model}</code>)
              </span>
              <span className="font-mono font-semibold text-emerald-300">
                ${tieredCost.toFixed(4)} / 1k runs (−{report.cost_reduction_pct.toFixed(2)}%)
              </span>
            </div>
            <div className="h-4 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-400 transition-all duration-500"
                style={{ width: `${tieredWidthPct}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
