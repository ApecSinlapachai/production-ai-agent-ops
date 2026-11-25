"use client";

import { useState } from "react";
import { CheckCircle2, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { ApiError, decideApproval } from "@/lib/api";
import type { ApprovalResponse, ApprovalStatus, RunDetailResponse } from "@/lib/types";
import { StateTimeline } from "./StateTimeline";
import { AgentStateBadge, ApprovalStatusBadge, RiskBadge } from "./StatusBadge";

interface ApprovalsQueueProps {
  approvals: ApprovalResponse[];
  loading: boolean;
  onRefresh: () => void;
}

export function ApprovalsQueue({ approvals, loading, onRefresh }: ApprovalsQueueProps) {
  const [statusFilter, setStatusFilter] = useState<"ALL" | ApprovalStatus>("ALL");
  const [reviewerName, setReviewerName] = useState("ops-reviewer-demo");
  const [reasonById, setReasonById] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [lastResumedRun, setLastResumedRun] = useState<RunDetailResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const filtered =
    statusFilter === "ALL"
      ? approvals
      : approvals.filter((item) => item.status === statusFilter);

  async function handleDecision(approvalId: string, decision: "APPROVED" | "REJECTED") {
    setSubmittingId(approvalId);
    setErrorMsg(null);
    try {
      const result = await decideApproval(approvalId, {
        decision,
        decided_by: reviewerName.trim() || "ops-reviewer-demo",
        decision_reason:
          reasonById[approvalId]?.trim() ||
          (decision === "APPROVED"
            ? "Verified synthetic refund policy & PII redaction."
            : "Rejected via Human-in-the-Loop control plane."),
      });
      setLastResumedRun(result.run);
      onRefresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.detail);
      } else {
        setErrorMsg("Failed to record HITL decision.");
      }
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/75 p-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <ShieldAlert className="h-4 w-4 text-amber-400" />
            Human-in-the-Loop (HITL) Approval Queue
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            High-impact external actions pause at <code className="text-amber-300">AWAITING_APPROVAL</code>{" "}
            with PostgreSQL <code className="text-slate-300">FOR UPDATE</code> row locking.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(["ALL", "PENDING", "APPROVED", "REJECTED"] as const).map((status) => (
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

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-2.5">
        <label htmlFor="reviewer-id" className="text-xs font-medium text-slate-300">
          Reviewer Identity:
        </label>
        <input
          id="reviewer-id"
          type="text"
          value={reviewerName}
          onChange={(e) => setReviewerName(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
        />
      </div>

      {errorMsg && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
          {errorMsg}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 text-center text-xs text-slate-400">
          No approval records match this filter. Trigger the &ldquo;TH Refund + Full PII (HITL Gate)&rdquo;
          scenario in Workflow Sandbox to create a <code className="text-amber-300">PENDING</code> gate.
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => {
            const isPending = item.status === "PENDING";
            const busy = submittingId === item.id;
            return (
              <div
                key={item.id}
                className="rounded-xl border border-slate-800 bg-slate-900/75 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <ApprovalStatusBadge status={item.status} />
                    <RiskBadge risk={item.risk_level} />
                    <span className="font-mono text-xs font-semibold text-slate-100">
                      {item.action_type}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-slate-400">
                    run: {item.run_id}
                  </span>
                </div>

                <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[11px] text-slate-300">
                  {JSON.stringify(item.action_preview, null, 2)}
                </pre>

                {isPending ? (
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <input
                      type="text"
                      value={reasonById[item.id] ?? ""}
                      onChange={(e) =>
                        setReasonById((prev) => ({ ...prev, [item.id]: e.target.value }))
                      }
                      placeholder="Optional audit reason (e.g., Policy verified)"
                      className="min-w-[240px] flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                    />
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleDecision(item.id, "REJECTED")}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/50 bg-rose-500/15 px-3 py-1.5 text-xs font-semibold text-rose-200 hover:bg-rose-500/25 disabled:opacity-50"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Reject
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleDecision(item.id, "APPROVED")}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-1.5 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {busy ? "Resuming..." : "Approve & Resume"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-2.5 flex flex-wrap items-center gap-4 text-xs text-slate-400">
                    <span>
                      Decided by: <strong className="text-slate-200">{item.decided_by}</strong>
                    </span>
                    {item.decision_reason && (
                      <span>
                        Reason: <span className="text-slate-300">{item.decision_reason}</span>
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {lastResumedRun && (
        <div className="space-y-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold text-emerald-200">
              Resumed Run Result ({lastResumedRun.id})
            </span>
            <AgentStateBadge state={lastResumedRun.current_state} />
          </div>
          <StateTimeline transitions={lastResumedRun.transitions} />
        </div>
      )}
    </div>
  );
}
