"""Pydantic v2 request and response schemas for agent runs and health status."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import AgentState, RoutingTier, RunSource, TransitionActor


class RunCreateRequest(BaseModel):
    """Payload to start an idempotent agent run."""

    message: str = Field(..., min_length=1, max_length=4000)
    customer_ref: str | None = Field(default=None, max_length=128)
    workflow_type: str = Field(default="customer_ops", min_length=1, max_length=64)
    source: RunSource = RunSource.API
    simulate_action_failure: bool = False


class N8nWebhookRequest(BaseModel):
    """Inbound webhook payload from an n8n workflow trigger."""

    message: str = Field(..., min_length=1, max_length=4000)
    customer_ref: str | None = Field(default=None, max_length=128)
    workflow_type: str = Field(default="customer_ops", min_length=1, max_length=64)
    event_id: str | None = Field(default=None, min_length=1, max_length=128)
    simulate_action_failure: bool = False


class RedactionSummary(BaseModel):
    """Aggregate PII redaction report without storing raw sensitive values."""

    total_redacted: int = Field(default=0, ge=0)
    entity_counts: dict[str, int] = Field(default_factory=dict)
    masked_previews: list[str] = Field(default_factory=list)


class StateTransitionResponse(BaseModel):
    """Single immutable audit-trail transition event."""

    id: int
    run_id: UUID
    from_state: AgentState | None = None
    to_state: AgentState
    actor: TransitionActor
    model_used: str | None = None
    routing_tier: RoutingTier | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RunResponse(BaseModel):
    """Summary representation of an `agent_runs` record."""

    id: UUID
    idempotency_key: str
    source: RunSource
    workflow_type: str
    customer_ref: str | None = None
    redacted_input: dict[str, Any]
    redaction_summary: RedactionSummary
    current_state: AgentState
    detected_intent: str | None = None
    routing_tier: RoutingTier | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_hitl: bool = False
    draft_response: str | None = None
    proposed_action: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    attempt_count: int = Field(default=0, ge=0)
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    total_latency_ms: int = Field(default=0, ge=0)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class RunDetailResponse(RunResponse):
    """Detailed run view including full state-transition timeline."""

    transitions: list[StateTransitionResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Service and database readiness payload for `/health`."""

    status: Literal["ok", "degraded"]
    database: Literal["connected", "degraded"]
    auth_mode: Literal["token", "demo_sandbox"]
    fast_model: str
    complex_model: str
