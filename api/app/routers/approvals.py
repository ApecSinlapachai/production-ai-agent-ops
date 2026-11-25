"""Human-in-the-Loop (HITL) approval queue endpoints (`/api/v1/approvals`)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_agent_engine, get_repository, require_api_auth
from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalResponse,
)
from app.schemas.enums import ApprovalStatus
from app.services.langgraph_engine import LangGraphAgentEngine
from app.services.repository import (
    AgentRepository,
    ApprovalStateConflictError,
    NotFoundError,
)

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["approvals"],
    dependencies=[Depends(require_api_auth)],
)

EngineDep = Annotated[LangGraphAgentEngine, Depends(get_agent_engine)]
RepoDep = Annotated[AgentRepository, Depends(get_repository)]


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(
    repo: RepoDep,
    approval_status: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ApprovalResponse]:
    """List HITL approval records, optionally filtered by status (e.g. PENDING)."""
    return repo.list_approvals(status=approval_status, limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(
    approval_id: UUID,
    repo: RepoDep,
) -> ApprovalResponse:
    """Fetch a single HITL approval record by ID."""
    try:
        return repo.get_approval(approval_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResponse)
def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    engine: EngineDep,
) -> ApprovalDecisionResponse:
    """Approve or reject a PENDING HITL gate and resume execution if approved."""
    decision = ApprovalStatus(payload.decision)
    try:
        return engine.decide_and_resume(
            approval_id=approval_id,
            decision=decision,
            decided_by=payload.decided_by,
            decision_reason=payload.decision_reason,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
