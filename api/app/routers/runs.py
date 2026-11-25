"""Agent run endpoints (`/api/v1/runs`) with boundary PDPA redaction and idempotency."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.dependencies import get_agent_engine, get_repository, require_api_auth
from app.schemas.agent import RunCreateRequest, RunDetailResponse, RunResponse
from app.schemas.enums import AgentState
from app.services.langgraph_engine import LangGraphAgentEngine
from app.services.repository import AgentRepository, IdempotencyConflictError, NotFoundError

router = APIRouter(
    prefix="/api/v1/runs",
    tags=["runs"],
    dependencies=[Depends(require_api_auth)],
)

EngineDep = Annotated[LangGraphAgentEngine, Depends(get_agent_engine)]
RepoDep = Annotated[AgentRepository, Depends(get_repository)]


@router.post("", response_model=RunDetailResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreateRequest,
    response: Response,
    engine: EngineDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RunDetailResponse:
    """Start an idempotent, PDPA-redacted state-machine agent run."""
    resolved_key = (idempotency_key or "").strip() or f"auto-{uuid4()}"

    try:
        run_detail, is_replayed = engine.start_run(payload, idempotency_key=resolved_key)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    response.headers["X-Idempotency-Replayed"] = "true" if is_replayed else "false"
    if is_replayed:
        response.status_code = status.HTTP_200_OK
    return run_detail


@router.get("", response_model=list[RunResponse])
def list_runs(
    repo: RepoDep,
    state: Annotated[AgentState | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunResponse]:
    """List agent runs ordered newest-first with optional state filtering."""
    return repo.list_runs(state=state, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: UUID,
    repo: RepoDep,
) -> RunDetailResponse:
    """Fetch a single agent run and its ordered state-transition audit trail."""
    try:
        return repo.get_run_detail(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
