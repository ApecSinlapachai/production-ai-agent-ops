"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration aligned with `.env.example`."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agent_ops"

    # Gemini API (Tiered Model Routing)
    gemini_api_key: str = ""
    gemini_fast_model: str = "gemini-3.5-flash-lite"
    gemini_complex_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = "gemini-3.1-flash-lite"

    # Security, Webhook & Public Demo Guardrails
    auth_mode: Literal["token", "demo_sandbox"] = "token"
    admin_api_token: str = "change-me-local-admin-token"
    n8n_webhook_secret: str = "change-me-n8n-webhook-secret"
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_min: int = Field(default=15, ge=1, le=1000)
    rate_limit_per_day: int = Field(default=60, ge=1, le=10000)

    # Reliability & Execution Policy
    max_retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: float = Field(default=1.0, ge=0.0, le=30.0)
    hitl_confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    @property
    def fallback_model_list(self) -> list[str]:
        """Parse comma-separated fallback model names into a clean list."""
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
