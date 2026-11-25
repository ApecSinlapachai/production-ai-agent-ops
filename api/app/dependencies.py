"""Shared FastAPI dependencies for authentication, repository, and LangGraph engine."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.config import Settings
from app.db import DatabasePool
from app.services.langgraph_engine import LangGraphAgentEngine
from app.services.rate_limiter import SlidingWindowRateLimiter, extract_client_ip, hash_client_ip
from app.services.repository import AgentRepository


def require_api_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Enforce AUTH_MODE=token (Bearer token) or AUTH_MODE=demo_sandbox (public demo)."""
    settings: Settings = request.app.state.settings
    if settings.auth_mode == "demo_sandbox":
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided_token, settings.admin_api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_webhook_secret(
    request: Request,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> None:
    """Always enforce X-Webhook-Secret for inbound n8n webhooks regardless of AUTH_MODE."""
    settings: Settings = request.app.state.settings
    if not x_webhook_secret or not hmac.compare_digest(
        x_webhook_secret.strip(), settings.n8n_webhook_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Webhook-Secret.",
        )


def enforce_rate_limit(request: Request) -> None:
    """Enforce IP-hashed sliding-window rate limits and return Retry-After on 429."""
    limiter: SlidingWindowRateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return

    ip_hash = hash_client_ip(extract_client_ip(request))
    allowed, retry_after = limiter.check_and_record(ip_hash)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry later.",
            headers={"Retry-After": str(retry_after)},
        )


def get_repository(request: Request) -> AgentRepository:
    """Return a repository bound to the app's PostgreSQL pool."""
    pool: DatabasePool = request.app.state.db_pool
    return AgentRepository(pool)


def get_agent_engine(request: Request) -> LangGraphAgentEngine:
    """Return a LangGraphAgentEngine bound to the app's DB pool and settings."""
    pool: DatabasePool = request.app.state.db_pool
    settings: Settings = request.app.state.settings
    return LangGraphAgentEngine(AgentRepository(pool), settings)
