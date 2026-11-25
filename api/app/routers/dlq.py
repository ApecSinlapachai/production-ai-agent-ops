"""Dead-Letter Queue (DLQ) inspection and replay endpoints (`/api/v1/dlq`)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    enforce_rate_limit,
    get_agent_engine,
    get_repository,
    require_api_auth,
)
from app.schemas.dlq import DLQJobResponse, DLQReplayResponse
from app.schemas.enums import DLQStatus
from app.services.langgraph_engine import LangGraphAgentEngine
from app.services.repository import (
    AgentRepository,
    DLQStateConflictError,
    NotFoundError,
)

router = APIRouter(
    prefix="/api/v1/dlq",
    tags=["dlq"],
    dependencies=[Depends(require_api_auth), Depends(enforce_rate_limit)],
)

EngineDep = Annotated[LangGraphAgentEngine, Depends(get_agent_engine)]
RepoDep = Annotated[AgentRepository, Depends(get_repository)]


@router.get("", response_model=list[DLQJobResponse])
def list_dlq_jobs(
    repo: RepoDep,
    dlq_status: Annotated[DLQStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DLQJobResponse]:
    """List dead-lettered jobs, optionally filtered by status (e.g. OPEN)."""
    return repo.list_dlq_jobs(status=dlq_status, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=DLQJobResponse)
def get_dlq_job(
    job_id: UUID,
    repo: RepoDep,
) -> DLQJobResponse:
    """Fetch a single Dead-Letter Queue job by ID."""
    try:
        return repo.get_dlq_job(job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{job_id}/replay", response_model=DLQReplayResponse)
def replay_dlq_job(
    job_id: UUID,
    engine: EngineDep,
    force_failure: Annotated[bool, Query()] = False,
) -> DLQReplayResponse:
    """Replay an OPEN DLQ job through the LangGraph execution graph."""
    try:
        return engine.replay_dlq_job(job_id, force_failure=force_failure)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DLQStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
