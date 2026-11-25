-- Production AI Agent Ops — Core PostgreSQL 16 / Supabase Schema
-- Idempotent DDL aligned 1:1 with api/app/schemas/enums.py & Pydantic v2 models.

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key TEXT NOT NULL UNIQUE,
    request_payload_hash TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('api', 'n8n', 'demo')),
    workflow_type TEXT NOT NULL DEFAULT 'customer_ops',
    customer_ref TEXT,
    redacted_input JSONB NOT NULL,
    redaction_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_state TEXT NOT NULL CHECK (
        current_state IN (
            'RECEIVED',
            'PII_REDACTED',
            'INTENT_ROUTED',
            'CONTEXT_FETCHED',
            'DRAFT_GENERATED',
            'AWAITING_APPROVAL',
            'APPROVED',
            'REJECTED',
            'EXECUTING_ACTION',
            'COMPLETED',
            'FAILED_RETRYING',
            'DLQ'
        )
    ),
    detected_intent TEXT,
    routing_tier TEXT CHECK (
        routing_tier IS NULL OR routing_tier IN ('FAST', 'COMPLEX', 'RULE_FALLBACK')
    ),
    confidence NUMERIC(4, 3) CHECK (
        confidence IS NULL OR (confidence >= 0.000 AND confidence <= 1.000)
    ),
    requires_hitl BOOLEAN NOT NULL DEFAULT FALSE,
    draft_response TEXT,
    proposed_action JSONB,
    execution_result JSONB,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    total_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_input_tokens >= 0),
    total_output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_output_tokens >= 0),
    total_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.000000 CHECK (total_cost_usd >= 0),
    total_latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (total_latency_ms >= 0),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_state_transitions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    from_state TEXT CHECK (
        from_state IS NULL OR from_state IN (
            'RECEIVED',
            'PII_REDACTED',
            'INTENT_ROUTED',
            'CONTEXT_FETCHED',
            'DRAFT_GENERATED',
            'AWAITING_APPROVAL',
            'APPROVED',
            'REJECTED',
            'EXECUTING_ACTION',
            'COMPLETED',
            'FAILED_RETRYING',
            'DLQ'
        )
    ),
    to_state TEXT NOT NULL CHECK (
        to_state IN (
            'RECEIVED',
            'PII_REDACTED',
            'INTENT_ROUTED',
            'CONTEXT_FETCHED',
            'DRAFT_GENERATED',
            'AWAITING_APPROVAL',
            'APPROVED',
            'REJECTED',
            'EXECUTING_ACTION',
            'COMPLETED',
            'FAILED_RETRYING',
            'DLQ'
        )
    ),
    actor TEXT NOT NULL CHECK (actor IN ('system', 'agent', 'human', 'dlq_replay')),
    model_used TEXT,
    routing_tier TEXT CHECK (
        routing_tier IS NULL OR routing_tier IN ('FAST', 'COMPLEX', 'RULE_FALLBACK')
    ),
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.000000 CHECK (cost_usd >= 0),
    latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hitl_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES agent_runs(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    action_preview JSONB NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')
    ),
    decided_by TEXT,
    decision_reason TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dead_letter_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    failed_state TEXT NOT NULL CHECK (
        failed_state IN (
            'RECEIVED',
            'PII_REDACTED',
            'INTENT_ROUTED',
            'CONTEXT_FETCHED',
            'DRAFT_GENERATED',
            'AWAITING_APPROVAL',
            'APPROVED',
            'REJECTED',
            'EXECUTING_ACTION',
            'COMPLETED',
            'FAILED_RETRYING',
            'DLQ'
        )
    ),
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    attempts_made INTEGER NOT NULL CHECK (attempts_made >= 1),
    payload_snapshot JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (
        status IN ('OPEN', 'REPLAYING', 'REPLAYED', 'DISCARDED')
    ),
    replay_count INTEGER NOT NULL DEFAULT 0 CHECK (replay_count >= 0),
    last_replayed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS llm_cost_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    routing_tier TEXT NOT NULL CHECK (
        routing_tier IN ('FAST', 'COMPLEX', 'RULE_FALLBACK')
    ),
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    estimated_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.000000 CHECK (estimated_cost_usd >= 0),
    latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_runs_updated_at ON agent_runs;
CREATE TRIGGER trg_agent_runs_updated_at
    BEFORE UPDATE ON agent_runs
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_dead_letter_jobs_updated_at ON dead_letter_jobs;
CREATE TRIGGER trg_dead_letter_jobs_updated_at
    BEFORE UPDATE ON dead_letter_jobs
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_agent_runs_state_created
    ON agent_runs (current_state, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_transitions_run_created
    ON agent_state_transitions (run_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_hitl_pending
    ON hitl_approvals (created_at ASC)
    WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_dlq_run_id
    ON dead_letter_jobs (run_id);

CREATE INDEX IF NOT EXISTS idx_dlq_open
    ON dead_letter_jobs (created_at ASC)
    WHERE status = 'OPEN';

CREATE INDEX IF NOT EXISTS idx_llm_cost_run_id
    ON llm_cost_logs (run_id);

CREATE INDEX IF NOT EXISTS idx_llm_cost_tier_created
    ON llm_cost_logs (routing_tier, created_at DESC);
