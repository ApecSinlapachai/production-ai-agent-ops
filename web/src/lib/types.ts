export type AgentState =
  | "RECEIVED"
  | "PII_REDACTED"
  | "INTENT_ROUTED"
  | "CONTEXT_FETCHED"
  | "DRAFT_GENERATED"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "EXECUTING_ACTION"
  | "COMPLETED"
  | "FAILED_RETRYING"
  | "DLQ";

export type RunSource = "api" | "n8n" | "demo";

export type RoutingTier = "FAST" | "COMPLEX" | "RULE_FALLBACK";

export type TransitionActor = "system" | "agent" | "human" | "dlq_replay";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";

export type DLQStatus = "OPEN" | "REPLAYING" | "REPLAYED" | "DISCARDED";

export interface HealthResponse {
  status: "ok" | "degraded";
  database: "connected" | "degraded";
  auth_mode: "token" | "demo_sandbox";
  fast_model: string;
  complex_model: string;
}

export interface RedactionSummary {
  total_redacted: number;
  entity_counts: Record<string, number>;
  masked_previews: string[];
}

export interface StateTransitionResponse {
  id: number;
  run_id: string;
  from_state: AgentState | null;
  to_state: AgentState;
  actor: TransitionActor;
  model_used: string | null;
  routing_tier: RoutingTier | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface RunResponse {
  id: string;
  idempotency_key: string;
  source: RunSource;
  workflow_type: string;
  customer_ref: string | null;
  redacted_input: Record<string, unknown>;
  redaction_summary: RedactionSummary;
  current_state: AgentState;
  detected_intent: string | null;
  routing_tier: RoutingTier | null;
  confidence: number | null;
  requires_hitl: boolean;
  draft_response: string | null;
  proposed_action: Record<string, unknown> | null;
  execution_result: Record<string, unknown> | null;
  attempt_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  total_latency_ms: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunDetailResponse extends RunResponse {
  transitions: StateTransitionResponse[];
}

export interface RunCreateRequest {
  message: string;
  customer_ref?: string | null;
  workflow_type?: string;
  source?: RunSource;
  simulate_action_failure?: boolean;
}

export interface ApprovalResponse {
  id: string;
  run_id: string;
  action_type: string;
  action_preview: Record<string, unknown>;
  risk_level: RiskLevel;
  status: ApprovalStatus;
  decided_by: string | null;
  decision_reason: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface ApprovalDecisionRequest {
  decision: "APPROVED" | "REJECTED";
  decided_by: string;
  decision_reason?: string | null;
}

export interface ApprovalDecisionResponse {
  approval: ApprovalResponse;
  run: RunDetailResponse;
}

export interface DLQJobResponse {
  id: string;
  run_id: string;
  failed_state: AgentState;
  error_code: string;
  error_message: string;
  attempts_made: number;
  payload_snapshot: Record<string, unknown>;
  status: DLQStatus;
  replay_count: number;
  last_replayed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DLQReplayResponse {
  job: DLQJobResponse;
  run_state: AgentState;
  message: string;
}

export interface BenchmarkReport {
  total_cases: number;
  fast_cases: number;
  complex_cases: number;
  pii_entities_redacted: number;
  pii_leak_rate: number;
  hitl_enforcement_rate: number;
  intent_accuracy: number;
  routing_accuracy: number;
  always_frontier: {
    model: string;
    total_input_tokens: number;
    total_output_tokens: number;
    total_cost_usd: number;
    cost_per_1000_runs_usd: number;
  };
  tiered_routing: {
    fast_model: string;
    complex_model: string;
    total_input_tokens: number;
    total_output_tokens: number;
    total_cost_usd: number;
    cost_per_1000_runs_usd: number;
  };
  cost_reduction_pct: number;
  thresholds: {
    max_pii_leak_rate: number;
    min_hitl_enforcement_rate: number;
    min_intent_accuracy: number;
    min_routing_accuracy: number;
    min_cost_reduction_pct: number;
    max_cost_reduction_pct: number;
  };
  gates_passed: boolean;
  gate_failures: string[];
}
