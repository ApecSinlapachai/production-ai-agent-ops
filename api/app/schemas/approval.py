"""Pydantic v2 schemas for Human-in-the-Loop (HITL) approval gates."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.agent import RunDetailResponse
from app.schemas.enums import ApprovalStatus, RiskLevel


class ApprovalDecisionRequest(BaseModel):
    """Human decision payload to approve or reject a pending HITL action."""

    decision: Literal["APPROVED", "REJECTED"]
    decided_by: str = Field(..., min_length=1, max_length=128)
    decision_reason: str | None = Field(default=None, max_length=1000)


class ApprovalResponse(BaseModel):
    """Representation of a `hitl_approvals` record."""

    id: UUID
    run_id: UUID
    action_type: str
    action_preview: dict[str, Any]
    risk_level: RiskLevel
    status: ApprovalStatus
    decided_by: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class ApprovalDecisionResponse(BaseModel):
    """Combined result returned after recording a HITL decision and any resumed execution."""

    approval: ApprovalResponse
    run: RunDetailResponse
