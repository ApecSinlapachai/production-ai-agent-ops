import type {
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  ApprovalResponse,
  ApprovalStatus,
  AgentState,
  BenchmarkReport,
  DLQJobResponse,
  DLQReplayResponse,
  DLQStatus,
  HealthResponse,
  RunCreateRequest,
  RunDetailResponse,
  RunResponse,
} from "./types";

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const API_BASE_URL = RAW_API_BASE.replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  retryAfterSeconds: number | null;
  detail: string;

  constructor(message: string, status: number, retryAfterSeconds: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
    this.detail = message;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<{ data: T; headers: Headers }> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const retryAfterHeader = response.headers.get("Retry-After");
    const retryAfter = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : null;
    let detail = `Request failed (${response.status})`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody?.detail) {
        detail = errBody.detail;
      }
    } catch {
      // Ignore non-JSON error payloads
    }
    throw new ApiError(detail, response.status, Number.isFinite(retryAfter) ? retryAfter : null);
  }

  const data = (await response.json()) as T;
  return { data, headers: response.headers };
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await requestJson<HealthResponse>("/health");
  return data;
}

export async function createRun(
  payload: RunCreateRequest,
  idempotencyKey?: string,
): Promise<{ data: RunDetailResponse; replayed: boolean }> {
  const headers: Record<string, string> = {};
  if (idempotencyKey && idempotencyKey.trim()) {
    headers["Idempotency-Key"] = idempotencyKey.trim();
  }
  const { data, headers: resHeaders } = await requestJson<RunDetailResponse>("/api/v1/runs", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const replayed = resHeaders.get("X-Idempotency-Replayed")?.toLowerCase() === "true";
  return { data, replayed };
}

export async function listRuns(state?: AgentState, limit = 25): Promise<RunResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (state) {
    params.set("state", state);
  }
  const { data } = await requestJson<RunResponse[]>(`/api/v1/runs?${params.toString()}`);
  return data;
}

export async function getRunDetail(runId: string): Promise<RunDetailResponse> {
  const { data } = await requestJson<RunDetailResponse>(`/api/v1/runs/${runId}`);
  return data;
}

export async function listApprovals(status?: ApprovalStatus, limit = 50): Promise<ApprovalResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  const { data } = await requestJson<ApprovalResponse[]>(`/api/v1/approvals?${params.toString()}`);
  return data;
}

export async function decideApproval(
  approvalId: string,
  payload: ApprovalDecisionRequest,
): Promise<ApprovalDecisionResponse> {
  const { data } = await requestJson<ApprovalDecisionResponse>(
    `/api/v1/approvals/${approvalId}/decision`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
  return data;
}

export async function listDlqJobs(status?: DLQStatus, limit = 50): Promise<DLQJobResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.set("status", status);
  }
  const { data } = await requestJson<DLQJobResponse[]>(`/api/v1/dlq?${params.toString()}`);
  return data;
}

export async function replayDlqJob(jobId: string, forceFailure = false): Promise<DLQReplayResponse> {
  const params = new URLSearchParams();
  if (forceFailure) {
    params.set("force_failure", "true");
  }
  const qs = params.toString();
  const { data } = await requestJson<DLQReplayResponse>(
    `/api/v1/dlq/${jobId}/replay${qs ? `?${qs}` : ""}`,
    {
      method: "POST",
    },
  );
  return data;
}

export async function fetchBenchmark(): Promise<BenchmarkReport> {
  const { data } = await requestJson<BenchmarkReport>("/api/v1/benchmark");
  return data;
}
