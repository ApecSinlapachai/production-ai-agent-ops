"""Inbound n8n webhook endpoints (`/webhooks/n8n`) protected by X-Webhook-Secret."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.dependencies import enforce_rate_limit, get_agent_engine, require_webhook_secret
from app.schemas.agent import N8nWebhookRequest, RunCreateRequest, RunDetailResponse
from app.schemas.enums import RunSource
from app.services.langgraph_engine import LangGraphAgentEngine
from app.services.repository import IdempotencyConflictError

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(require_webhook_secret), Depends(enforce_rate_limit)],
)

EngineDep = Annotated[LangGraphAgentEngine, Depends(get_agent_engine)]


@router.post("/n8n", response_model=RunDetailResponse, status_code=status.HTTP_201_CREATED)
def ingest_n8n_webhook(
    payload: N8nWebhookRequest,
    response: Response,
    engine: EngineDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RunDetailResponse:
    """Receive an n8n webhook event, enforce idempotency, redact PII, and run the agent."""
    header_key = (idempotency_key or "").strip()
    if header_key:
        resolved_key = header_key
    elif payload.event_id:
        resolved_key = f"n8n-{payload.event_id}"
    else:
        resolved_key = f"n8n-{uuid4()}"

    run_request = RunCreateRequest(
        message=payload.message,
        customer_ref=payload.customer_ref,
        workflow_type=payload.workflow_type,
        source=RunSource.N8N,
        simulate_action_failure=payload.simulate_action_failure,
    )

    try:
        run_detail, is_replayed = engine.start_run(run_request, idempotency_key=resolved_key)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    response.headers["X-Idempotency-Replayed"] = "true" if is_replayed else "false"
    if is_replayed:
        response.status_code = status.HTTP_200_OK
    return run_detail
