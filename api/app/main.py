"""FastAPI application entrypoint, lifespan management, and health endpoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.db import DatabasePool
from app.routers import approvals, benchmark, dlq, runs, webhooks
from app.schemas.agent import HealthResponse
from app.services.rate_limiter import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage PostgreSQL pool lifecycle cleanly across app startup and shutdown."""
    settings: Settings = app.state.settings
    pool = DatabasePool(settings.database_url)
    app.state.db_pool = pool

    try:
        pool.open()
    except Exception as exc:  # pragma: no cover - degraded startup path
        logger.warning("Database pool did not open on startup (will report degraded): %s", exc)

    yield

    pool.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application instance."""
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title="Production AI Agent Ops API",
        version="0.1.0",
        description=(
            "State-Machine AI Operations Agent with HITL Approval Gates, "
            "PDPA PII Redaction, Idempotent Retry + DLQ, and Tiered Model Routing."
        ),
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.rate_limiter = SlidingWindowRateLimiter(
        per_minute=resolved_settings.rate_limit_per_min,
        per_day=resolved_settings.rate_limit_per_day,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-Webhook-Secret"],
        expose_headers=["Retry-After", "X-Idempotency-Replayed"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health(request: Request) -> HealthResponse:
        """Report service readiness and database connectivity."""
        pool: DatabasePool = request.app.state.db_pool
        db_ok = pool.check_health()
        return HealthResponse(
            status="ok" if db_ok else "degraded",
            database="connected" if db_ok else "degraded",
            auth_mode=resolved_settings.auth_mode,
            fast_model=resolved_settings.gemini_fast_model,
            complex_model=resolved_settings.gemini_complex_model,
        )

    app.include_router(runs.router)
    app.include_router(approvals.router)
    app.include_router(dlq.router)
    app.include_router(webhooks.router)
    app.include_router(benchmark.router)

    return app


app = create_app()
