"use client";

import { useState } from "react";
import { AlertOctagon, RefreshCw, RotateCcw } from "lucide-react";
import { ApiError, replayDlqJob } from "@/lib/api";
import type { DLQJobResponse, DLQReplayResponse, DLQStatus } from "@/lib/types";
import { AgentStateBadge, DlqStatusBadge } from "./StatusBadge";

interface DlqPanelProps {
  jobs: DLQJobResponse[];
  loading: boolean;
  onRefresh: () => void;
}

export function DlqPanel({ jobs, loading, onRefresh }: DlqPanelProps) {
  const [statusFilter, setStatusFilter] = useState<"ALL" | DLQStatus>("ALL");
  const [replayingId, setReplayingId] = useState<string | null>(null);
  const [lastReplay, setLastReplay] = useState<DLQReplayResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const filtered =
    statusFilter === "ALL" ? jobs : jobs.filter((job) => job.status === statusFilter);

  async function handleReplay(jobId: string) {
    setReplayingId(jobId);
    setErrorMsg(null);
    try {
      const res = await replayDlqJob(jobId, false);
      setLastReplay(res);
      onRefresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.detail);
      } else {
        setErrorMsg("Failed to replay DLQ job.");
      }
    } finally {
      setReplayingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/75 p-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <AlertOctagon className="h-4 w-4 text-rose-400" />
            Dead-Letter Queue (DLQ) &amp; Manual Replay
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Jobs exhausting bounded exponential backoff land here with PII-redacted snapshots.
            Replay executes under <code className="text-slate-300">FOR UPDATE</code> locking.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(["ALL", "OPEN", "REPLAYED"] as const).map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(status)}
              className={`rounded-lg border px-2.5 py-1 font-mono text-xs transition ${
                statusFilter === status
                  ? "border-cyan-500/60 bg-cyan-500/15 text-cyan-200"
                  : "border-slate-700 bg-slate-950 text-slate-400 hover:text-slate-200"
              }`}
            >
              {status}
            </button>
          ))}
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

      {errorMsg && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
          {errorMsg}
        </div>
      )}

      {lastReplay && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-200">
          <span>
            Replayed DLQ job <code className="font-mono">{lastReplay.job.id}</code>:{" "}
            {lastReplay.message}
          </span>
          <AgentStateBadge state={lastReplay.run_state} />
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 text-center text-xs text-slate-400">
          No DLQ jobs match this filter. Run the &ldquo;Simulated Downstream Failure → DLQ&rdquo;
          scenario in Workflow Sandbox to observe retry exhaustion and DLQ capture.
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((job) => {
            const isOpen = job.status === "OPEN";
            const busy = replayingId === job.id;
            return (
              <div
                key={job.id}
                className="rounded-xl border border-slate-800 bg-slate-900/75 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <DlqStatusBadge status={job.status} />
                    <span className="rounded bg-rose-500/10 px-2 py-0.5 font-mono text-xs text-rose-300">
                      {job.error_code}
                    </span>
                    <span className="font-mono text-xs text-slate-300">
                      attempts: {job.attempts_made} • replays: {job.replay_count}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-slate-400">
                    run: {job.run_id}
                  </span>
                </div>

                <p className="mt-2 text-xs text-slate-200">{job.error_message}</p>

                <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[11px] text-slate-300">
                  {JSON.stringify(job.payload_snapshot, null, 2)}
                </pre>

                {isOpen && (
                  <div className="mt-3 flex justify-end">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleReplay(job.id)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500 px-3.5 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
                    >
                      <RotateCcw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
                      {busy ? "Replaying..." : "Replay Job"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
