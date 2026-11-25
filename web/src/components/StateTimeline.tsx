"use client";

import { ArrowRight, Clock, Cpu, GitCommitHorizontal } from "lucide-react";
import type { StateTransitionResponse } from "@/lib/types";
import { AgentStateBadge, TierBadge } from "./StatusBadge";

interface StateTimelineProps {
  transitions: StateTransitionResponse[];
}

export function StateTimeline({ transitions }: StateTimelineProps) {
  if (transitions.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-xs text-slate-400">
        No transitions recorded yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCommitHorizontal className="h-4 w-4 text-indigo-400" />
          <h3 className="text-sm font-semibold text-slate-100">
            LangGraph State-Machine Audit Trail ({transitions.length} transitions)
          </h3>
        </div>
        <span className="font-mono text-[11px] text-slate-400">SQL-Persisted</span>
      </div>

      <ol className="space-y-2.5">
        {transitions.map((t, index) => (
          <li
            key={t.id}
            className="rounded-lg border border-slate-800/90 bg-slate-950/75 px-3 py-2.5"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[11px] text-slate-500">#{index + 1}</span>
                {t.from_state ? (
                  <>
                    <AgentStateBadge state={t.from_state} />
                    <ArrowRight className="h-3.5 w-3.5 text-slate-500" />
                  </>
                ) : (
                  <span className="font-mono text-[11px] text-slate-500">INIT →</span>
                )}
                <AgentStateBadge state={t.to_state} />
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                  actor:{t.actor}
                </span>
                <TierBadge tier={t.routing_tier} />
              </div>

              <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-slate-400">
                {t.model_used && (
                  <span className="inline-flex items-center gap-1 text-slate-300">
                    <Cpu className="h-3 w-3 text-slate-400" />
                    {t.model_used}
                  </span>
                )}
                {(t.input_tokens > 0 || t.output_tokens > 0) && (
                  <span>
                    {t.input_tokens}in / {t.output_tokens}out
                  </span>
                )}
                {t.cost_usd > 0 && (
                  <span className="text-emerald-300">${t.cost_usd.toFixed(6)}</span>
                )}
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {t.latency_ms}ms
                </span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
