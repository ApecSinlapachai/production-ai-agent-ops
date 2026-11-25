"use client";

import type {
  AgentState,
  ApprovalStatus,
  DLQStatus,
  RiskLevel,
  RoutingTier,
} from "@/lib/types";

const STATE_STYLES: Record<AgentState, string> = {
  RECEIVED: "border-slate-600/60 bg-slate-800/70 text-slate-200",
  PII_REDACTED: "border-cyan-500/40 bg-cyan-500/10 text-cyan-300",
  INTENT_ROUTED: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  CONTEXT_FETCHED: "border-indigo-500/40 bg-indigo-500/10 text-indigo-300",
  DRAFT_GENERATED: "border-violet-500/40 bg-violet-500/10 text-violet-300",
  AWAITING_APPROVAL: "border-amber-500/50 bg-amber-500/15 text-amber-300",
  APPROVED: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  REJECTED: "border-rose-500/50 bg-rose-500/15 text-rose-300",
  EXECUTING_ACTION: "border-blue-500/40 bg-blue-500/10 text-blue-300",
  COMPLETED: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
  FAILED_RETRYING: "border-orange-500/50 bg-orange-500/15 text-orange-300",
  DLQ: "border-rose-500/60 bg-rose-500/20 text-rose-200",
};

const TIER_STYLES: Record<RoutingTier, string> = {
  FAST: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  COMPLEX: "border-purple-500/40 bg-purple-500/10 text-purple-300",
  RULE_FALLBACK: "border-slate-500/40 bg-slate-700/40 text-slate-300",
};

const RISK_STYLES: Record<RiskLevel, string> = {
  LOW: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  MEDIUM: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  HIGH: "border-rose-500/50 bg-rose-500/15 text-rose-300",
};

const APPROVAL_STYLES: Record<ApprovalStatus, string> = {
  PENDING: "border-amber-500/50 bg-amber-500/15 text-amber-300",
  APPROVED: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
  REJECTED: "border-rose-500/50 bg-rose-500/15 text-rose-300",
  EXPIRED: "border-slate-600/50 bg-slate-800/70 text-slate-400",
};

const DLQ_STYLES: Record<DLQStatus, string> = {
  OPEN: "border-rose-500/50 bg-rose-500/15 text-rose-300",
  REPLAYING: "border-amber-500/50 bg-amber-500/15 text-amber-300",
  REPLAYED: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
  DISCARDED: "border-slate-600/50 bg-slate-800/70 text-slate-400",
};

export function AgentStateBadge({ state }: { state: AgentState }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium tracking-tight ${STATE_STYLES[state]}`}
    >
      {state}
    </span>
  );
}

export function TierBadge({ tier }: { tier: RoutingTier | null }) {
  if (!tier) return null;
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] font-medium ${TIER_STYLES[tier]}`}
    >
      {tier}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] font-medium ${RISK_STYLES[risk]}`}
    >
      RISK: {risk}
    </span>
  );
}

export function ApprovalStatusBadge({ status }: { status: ApprovalStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium ${APPROVAL_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

export function DlqStatusBadge({ status }: { status: DLQStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium ${DLQ_STYLES[status]}`}
    >
      {status}
    </span>
  );
}
