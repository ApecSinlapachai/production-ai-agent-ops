"use client";

import { Activity, Cpu, RefreshCw, ShieldCheck, WifiOff } from "lucide-react";
import type { HealthResponse } from "@/lib/types";

interface HealthBannerProps {
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
  wakingUp: boolean;
  onRetry: () => void;
}

export function HealthBanner({
  health,
  loading,
  error,
  wakingUp,
  onRetry,
}: HealthBannerProps) {
  const isOk = health?.status === "ok" && health?.database === "connected";

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            {loading || wakingUp ? (
              <RefreshCw className="h-4 w-4 animate-spin text-amber-400" />
            ) : isOk ? (
              <Activity className="h-4 w-4 text-emerald-400" />
            ) : (
              <WifiOff className="h-4 w-4 text-rose-400" />
            )}
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              API Status:
            </span>
            {loading || wakingUp ? (
              <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 font-mono text-xs text-amber-300">
                {wakingUp ? "Waking Render Free Instance..." : "Checking /health..."}
              </span>
            ) : isOk ? (
              <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-xs text-emerald-300">
                ONLINE • PG16 CONNECTED
              </span>
            ) : (
              <span className="rounded-full border border-rose-500/40 bg-rose-500/10 px-2.5 py-0.5 font-mono text-xs text-rose-300">
                {health ? `DEGRADED (${health.database})` : "UNREACHABLE"}
              </span>
            )}
          </div>

          {health && (
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-0.5 font-mono">
                <ShieldCheck className="h-3.5 w-3.5 text-cyan-400" />
                auth: {health.auth_mode}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-0.5 font-mono">
                <Cpu className="h-3.5 w-3.5 text-emerald-400" />
                FAST: {health.fast_model}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-0.5 font-mono">
                <Cpu className="h-3.5 w-3.5 text-purple-400" />
                COMPLEX: {health.complex_model}
              </span>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onRetry}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-slate-600 hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Ping /health
        </button>
      </div>

      {error && (
        <p className="mt-2 text-xs text-amber-300/90">
          {error} Free-tier containers sleep after inactivity and usually wake within 20-40 seconds.
        </p>
      )}
    </div>
  );
}
