"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CopyCheck,
  KeyRound,
  Play,
  RefreshCw,
  Send,
  Sparkles,
} from "lucide-react";
import { ApiError, createRun, getRunDetail } from "@/lib/api";
import { SCENARIO_PRESETS, type ScenarioPreset } from "@/lib/presets";
import type { RunDetailResponse, RunResponse } from "@/lib/types";
import { PiiDiffViewer } from "./PiiDiffViewer";
import { StateTimeline } from "./StateTimeline";
import { AgentStateBadge, TierBadge } from "./StatusBadge";

interface WorkflowSandboxProps {
  recentRuns: RunResponse[];
  onRunCompleted: () => void;
  onNavigateTab: (tab: "sandbox" | "approvals" | "dlq" | "benchmark") => void;
}

function generateIdempotencyKey(): string {
  const shortId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `demo-${shortId}`;
}

export function WorkflowSandbox({
  recentRuns,
  onRunCompleted,
  onNavigateTab,
}: WorkflowSandboxProps) {
  const defaultPreset = SCENARIO_PRESETS[2];
  const [selectedPresetId, setSelectedPresetId] = useState<string>(defaultPreset.id);
  const [message, setMessage] = useState<string>(defaultPreset.message);
  const [customerRef, setCustomerRef] = useState<string>(defaultPreset.customerRef);
  const [simulateFailure, setSimulateFailure] = useState<boolean>(
    defaultPreset.simulateActionFailure,
  );
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => generateIdempotencyKey());
  const [lastOriginalMessage, setLastOriginalMessage] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<RunDetailResponse | null>(null);
  const [wasReplayed, setWasReplayed] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function applyPreset(preset: ScenarioPreset) {
    setSelectedPresetId(preset.id);
    setMessage(preset.message);
    setCustomerRef(preset.customerRef);
    setSimulateFailure(preset.simulateActionFailure);
    setIdempotencyKey(generateIdempotencyKey());
    setErrorMsg(null);
  }

  async function executeRun(keepSameKey: boolean) {
    const keyToUse = keepSameKey ? idempotencyKey : generateIdempotencyKey();
    if (!keepSameKey) {
      setIdempotencyKey(keyToUse);
    }

    setSubmitting(true);
    setErrorMsg(null);

    try {
      const { data, replayed } = await createRun(
        {
          message,
          customer_ref: customerRef.trim() || null,
          workflow_type: "customer_ops",
          source: "demo",
          simulate_action_failure: simulateFailure,
        },
        keyToUse,
      );
      setLastOriginalMessage(message);
      setActiveRun(data);
      setWasReplayed(replayed);
      onRunCompleted();
    } catch (err) {
      if (err instanceof ApiError) {
        const retryNote =
          err.status === 429 && err.retryAfterSeconds
            ? ` Retry after ${err.retryAfterSeconds}s.`
            : "";
        setErrorMsg(`${err.detail}${retryNote}`);
      } else {
        setErrorMsg("Unable to reach backend API. Check /health banner above.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleInspectRun(runId: string) {
    setLoadingRunId(runId);
    setErrorMsg(null);
    try {
      const detail = await getRunDetail(runId);
      setActiveRun(detail);
      setLastOriginalMessage(null);
      setWasReplayed(false);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load run details.");
    } finally {
      setLoadingRunId(null);
    }
  }

  const redactedMsg =
    typeof activeRun?.redacted_input?.message === "string"
      ? activeRun.redacted_input.message
      : "";

  return (
    <div className="space-y-6">
      {/* Preset Scenario Cards */}
      <div>
        <div className="mb-2.5 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-100">
            1. Choose a Synthetic TH/EN Scenario (Zero Real PII)
          </h2>
          <span className="text-xs text-slate-400">
            Click a scenario to load synthetic payload &amp; fresh Idempotency-Key
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {SCENARIO_PRESETS.map((preset) => {
            const active = preset.id === selectedPresetId;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyPreset(preset)}
                className={`rounded-xl border p-3.5 text-left transition ${
                  active
                    ? "border-cyan-500/60 bg-cyan-500/10 shadow-sm shadow-cyan-500/10"
                    : "border-slate-800 bg-slate-900/70 hover:border-slate-700 hover:bg-slate-900"
                }`}
              >
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[10px] font-semibold text-cyan-300">
                    {preset.badge}
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-100">{preset.label}</div>
                <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-400">
                  {preset.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Two-Column Grid: Trigger Form + Recent Runs */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900/75 p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Sparkles className="h-4 w-4 text-cyan-400" />
              2. Trigger Idempotent Agent Run
            </h2>
            <span className="font-mono text-[11px] text-slate-400">POST /api/v1/runs</span>
          </div>

          <div className="space-y-3">
            <div>
              <label
                htmlFor="run-message"
                className="mb-1 block text-xs font-medium text-slate-300"
              >
                Customer / Webhook Message (TH or EN)
              </label>
              <textarea
                id="run-message"
                rows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                maxLength={4000}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Enter synthetic customer support request..."
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="customer-ref"
                  className="mb-1 block text-xs font-medium text-slate-300"
                >
                  Customer Reference
                </label>
                <input
                  id="customer-ref"
                  type="text"
                  value={customerRef}
                  onChange={(e) => setCustomerRef(e.target.value)}
                  maxLength={128}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="idempotency-key"
                  className="mb-1 block text-xs font-medium text-slate-300"
                >
                  Idempotency-Key Header
                </label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <KeyRound className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                    <input
                      id="idempotency-key"
                      type="text"
                      value={idempotencyKey}
                      onChange={(e) => setIdempotencyKey(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-8 pr-2.5 font-mono text-xs text-slate-100 focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setIdempotencyKey(generateIdempotencyKey())}
                    className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-2 text-xs text-slate-200 hover:bg-slate-700"
                    title="Generate fresh Idempotency-Key"
                  >
                    New
                  </button>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={simulateFailure}
                  onChange={(e) => setSimulateFailure(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-cyan-500 focus:ring-cyan-500"
                />
                <span>Simulate downstream execution failure (tests 3x retry → DLQ)</span>
              </label>

              <div className="flex flex-wrap items-center gap-2">
                {activeRun && (
                  <button
                    type="button"
                    disabled={submitting || !message.trim()}
                    onClick={() => executeRun(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/50 bg-indigo-500/15 px-3 py-2 text-xs font-semibold text-indigo-200 transition hover:bg-indigo-500/25 disabled:opacity-50"
                  >
                    <CopyCheck className="h-3.5 w-3.5" />
                    Test Idempotent Replay (Same Key)
                  </button>
                )}

                <button
                  type="button"
                  disabled={submitting || !message.trim()}
                  onClick={() => executeRun(true)}
                  className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
                >
                  {submitting ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5" />
                  )}
                  {submitting ? "Executing Graph..." : "Run Agent Workflow"}
                </button>
              </div>
            </div>

            {errorMsg && (
              <div className="flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
                <span>{errorMsg}</span>
              </div>
            )}
          </div>
        </div>

        {/* Recent Runs Selector */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/75 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-100">Recent Runs (PostgreSQL)</h3>
            <span className="font-mono text-[11px] text-slate-400">{recentRuns.length} loaded</span>
          </div>

          {recentRuns.length === 0 ? (
            <p className="text-xs text-slate-400">
              No runs yet. Trigger a scenario on the left to inspect state transitions.
            </p>
          ) : (
            <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {recentRuns.map((run) => {
                const selected = activeRun?.id === run.id;
                return (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => handleInspectRun(run.id)}
                    className={`w-full rounded-lg border p-2.5 text-left transition ${
                      selected
                        ? "border-cyan-500/60 bg-cyan-500/10"
                        : "border-slate-800 bg-slate-950/70 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <AgentStateBadge state={run.current_state} />
                      <TierBadge tier={run.routing_tier} />
                    </div>
                    <div className="mt-1.5 flex items-center justify-between font-mono text-[10px] text-slate-400">
                      <span>{run.detected_intent ?? "pending"}</span>
                      <span>{loadingRunId === run.id ? "loading..." : run.id.slice(0, 8)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Active Run Inspector */}
      {activeRun && (
        <div className="space-y-4">
          {/* Summary Banner */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-mono text-xs text-slate-400">RUN {activeRun.id}</span>
                <AgentStateBadge state={activeRun.current_state} />
                <TierBadge tier={activeRun.routing_tier} />
                {wasReplayed && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-indigo-400/50 bg-indigo-500/20 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-indigo-200">
                    <CopyCheck className="h-3 w-3" />
                    X-Idempotency-Replayed: true (200 OK — zero duplicate execution)
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {activeRun.current_state === "AWAITING_APPROVAL" && (
                  <button
                    type="button"
                    onClick={() => onNavigateTab("approvals")}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/50 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:bg-amber-500/25"
                  >
                    <Send className="h-3.5 w-3.5" />
                    Open HITL Approval Queue →
                  </button>
                )}
                {activeRun.current_state === "DLQ" && (
                  <button
                    type="button"
                    onClick={() => onNavigateTab("dlq")}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/50 bg-rose-500/15 px-3 py-1.5 text-xs font-semibold text-rose-200 hover:bg-rose-500/25"
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Inspect &amp; Replay in DLQ →
                  </button>
                )}
              </div>
            </div>

            <div className="mt-3 grid gap-3 border-t border-slate-800 pt-3 text-xs sm:grid-cols-4">
              <div>
                <div className="text-slate-400">Detected Intent</div>
                <div className="mt-0.5 font-mono font-semibold text-slate-100">
                  {activeRun.detected_intent ?? "N/A"}
                  {activeRun.confidence !== null && (
                    <span className="ml-1.5 text-slate-400">
                      ({(activeRun.confidence * 100).toFixed(0)}%)
                    </span>
                  )}
                </div>
              </div>
              <div>
                <div className="text-slate-400">Tokens (In / Out)</div>
                <div className="mt-0.5 font-mono font-semibold text-slate-100">
                  {activeRun.total_input_tokens} / {activeRun.total_output_tokens}
                </div>
              </div>
              <div>
                <div className="text-slate-400">Total Cost (USD)</div>
                <div className="mt-0.5 font-mono font-semibold text-emerald-300">
                  ${activeRun.total_cost_usd.toFixed(6)}
                </div>
              </div>
              <div>
                <div className="text-slate-400">Latency / Attempts</div>
                <div className="mt-0.5 font-mono font-semibold text-slate-100">
                  {activeRun.total_latency_ms}ms ({activeRun.attempt_count} attempts)
                </div>
              </div>
            </div>
          </div>

          <PiiDiffViewer
            originalMessage={lastOriginalMessage}
            redactedMessage={redactedMsg}
            summary={activeRun.redaction_summary}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-100">
                Draft Response &amp; Proposed Action
              </h3>
              <p className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs leading-relaxed text-slate-200">
                {activeRun.draft_response ?? "No draft generated."}
              </p>
              {activeRun.proposed_action && (
                <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[11px] text-slate-300">
                  {JSON.stringify(activeRun.proposed_action, null, 2)}
                </pre>
              )}
              {activeRun.execution_result && (
                <div className="mt-3">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                    Execution Result
                  </div>
                  <pre className="overflow-x-auto rounded-lg border border-emerald-500/30 bg-slate-950 p-3 font-mono text-[11px] text-emerald-200">
                    {JSON.stringify(activeRun.execution_result, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <StateTimeline transitions={activeRun.transitions} />
          </div>
        </div>
      )}
    </div>
  );
}
