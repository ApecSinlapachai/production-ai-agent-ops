"""Pydantic v2 schemas for Dead-Letter Queue (DLQ) inspection and replay."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import AgentState, DLQStatus


class DLQJobResponse(BaseModel):
    """Representation of a `dead_letter_jobs` record."""

    id: UUID
    run_id: UUID
    failed_state: AgentState
    error_code: str
    error_message: str
    attempts_made: int = Field(..., ge=1)
    payload_snapshot: dict[str, Any]
    status: DLQStatus
    replay_count: int = Field(default=0, ge=0)
    last_replayed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DLQReplayResponse(BaseModel):
    """Result of replaying a dead-lettered job."""

    job: DLQJobResponse
    run_state: AgentState
    message: str
