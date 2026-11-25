"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertOctagon,
  BarChart3,
  Bot,
  ShieldAlert,
  Workflow,
} from "lucide-react";
import {
  API_PROXY_PREFIX,
  fetchBenchmark,
  fetchHealth,
  listApprovals,
  listDlqJobs,
  listRuns,
} from "@/lib/api";
import type {
  ApprovalResponse,
  BenchmarkReport,
  DLQJobResponse,
  HealthResponse,
  RunResponse,
} from "@/lib/types";
import { ApprovalsQueue } from "@/components/ApprovalsQueue";
import { BenchmarkScorecard } from "@/components/BenchmarkScorecard";
import { DlqPanel } from "@/components/DlqPanel";
import { HealthBanner } from "@/components/HealthBanner";
import { WorkflowSandbox } from "@/components/WorkflowSandbox";

type TabId = "sandbox" | "approvals" | "dlq" | "benchmark";

const HEALTH_RETRY_INTERVAL_MS = 5000;
const HEALTH_MAX_RETRIES = 10;

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabId>("sandbox");

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [wakingUp, setWakingUp] = useState(false);

  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [dlqJobs, setDlqJobs] = useState<DLQJobResponse[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const [dataLoading, setDataLoading] = useState(false);

  const loadOperationalData = useCallback(async () => {
    setDataLoading(true);
    try {
      const [runsRes, approvalsRes, dlqRes] = await Promise.all([
        listRuns(undefined, 25),
        listApprovals(undefined, 50),
        listDlqJobs(undefined, 50),
      ]);
      setRuns(runsRes);
      setApprovals(approvalsRes);
      setDlqJobs(dlqRes);
    } catch {
      // Errors are surfaced via HealthBanner when backend is waking or unreachable
    } finally {
      setDataLoading(false);
    }
  }, []);

  const loadBenchmark = useCallback(async () => {
    try {
      const report = await fetchBenchmark();
      setBenchmark(report);
      setBenchmarkError(null);
    } catch (err) {
      setBenchmarkError(
        err instanceof Error ? err.message : "Failed to load benchmark scorecard.",
      );
    }
  }, []);

  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const checkHealth = useCallback(
    async (attempt = 0) => {
      clearRetryTimer();
      setHealthLoading(true);
      if (attempt === 0) {
        setHealthError(null);
      }
      try {
        const res = await fetchHealth();
        if (!mountedRef.current) return;
        setHealth(res);
        setWakingUp(false);
        setHealthError(null);
        setHealthLoading(false);
        await Promise.all([loadOperationalData(), loadBenchmark()]);
      } catch {
        if (!mountedRef.current) return;
        setHealth(null);
        if (attempt < HEALTH_MAX_RETRIES) {
          const nextAttempt = attempt + 1;
          setWakingUp(true);
          setHealthError(
            `Waiting for API via ${API_PROXY_PREFIX} (retry ${nextAttempt}/${HEALTH_MAX_RETRIES})...`,
          );
          setHealthLoading(false);
          retryTimerRef.current = setTimeout(() => {
            void checkHealth(nextAttempt);
          }, HEALTH_RETRY_INTERVAL_MS);
        } else {
          setWakingUp(false);
          setHealthError(
            `Could not connect to API via ${API_PROXY_PREFIX} after ${HEALTH_MAX_RETRIES} retries.`,
          );
          setHealthLoading(false);
        }
      }
    },
    [clearRetryTimer, loadBenchmark, loadOperationalData],
  );

  useEffect(() => {
    mountedRef.current = true;
    void checkHealth(0);
    return () => {
      mountedRef.current = false;
      clearRetryTimer();
    };
  }, [checkHealth, clearRetryTimer]);

  const pendingApprovalsCount = approvals.filter((a) => a.status === "PENDING").length;
  const openDlqCount = dlqJobs.filter((j) => j.status === "OPEN").length;

  const tabs: {
    id: TabId;
    label: string;
    icon: typeof Workflow;
    badge?: number;
    badgeColor?: string;
  }[] = [
    { id: "sandbox", label: "Workflow Sandbox", icon: Workflow },
    {
      id: "approvals",
      label: "HITL Approvals",
      icon: ShieldAlert,
      badge: pendingApprovalsCount,
      badgeColor: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    },
    {
      id: "dlq",
      label: "Dead-Letter Queue",
      icon: AlertOctagon,
      badge: openDlqCount,
      badgeColor: "bg-rose-500/20 text-rose-300 border-rose-500/40",
    },
    { id: "benchmark", label: "Cost Benchmark", icon: BarChart3 },
  ];

  return (
    <div className="mx-auto min-h-screen max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <header className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-500/40 bg-cyan-500/15">
              <Bot className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-slate-50 sm:text-xl">
                Production AI Agent Ops
              </h1>
              <p className="text-xs text-slate-400">
                No-Login Live Control Plane • LangGraph State Machine • PDPA Redaction • HITL •
                Idempotent Retry + DLQ
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 font-mono">
            endpoint: {API_PROXY_PREFIX} (same-origin proxy)
          </span>
        </div>
      </header>

      {/* Cold-Start & Health Banner */}
      <div className="mb-5">
        <HealthBanner
          health={health}
          loading={healthLoading}
          error={healthError}
          wakingUp={wakingUp}
          onRetry={() => void checkHealth(0)}
        />
      </div>

      {/* Navigation Tabs */}
      <nav className="mb-6 flex flex-wrap gap-2 border-b border-slate-800 pb-3">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold transition ${
                active
                  ? "border-cyan-500/60 bg-cyan-500/15 text-cyan-200"
                  : "border-slate-800 bg-slate-900/70 text-slate-300 hover:border-slate-700 hover:bg-slate-900"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
              {typeof tab.badge === "number" && tab.badge > 0 && (
                <span
                  className={`rounded-full border px-1.5 py-0.2 font-mono text-[10px] ${tab.badgeColor}`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Tab Content */}
      <main>
        {activeTab === "sandbox" && (
          <WorkflowSandbox
            recentRuns={runs}
            onRunCompleted={() => void loadOperationalData()}
            onNavigateTab={setActiveTab}
          />
        )}

        {activeTab === "approvals" && (
          <ApprovalsQueue
            approvals={approvals}
            loading={dataLoading}
            onRefresh={() => void loadOperationalData()}
          />
        )}

        {activeTab === "dlq" && (
          <DlqPanel
            jobs={dlqJobs}
            loading={dataLoading}
            onRefresh={() => void loadOperationalData()}
          />
        )}

        {activeTab === "benchmark" && (
          <BenchmarkScorecard
            report={benchmark}
            loading={dataLoading}
            error={benchmarkError}
            onRefresh={() => void loadBenchmark()}
          />
        )}
      </main>
    </div>
  );
}
