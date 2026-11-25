"""Unit tests for application configuration."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_settings_preserve_gemini_3x_models() -> None:
    """Default model configuration matches the Gemini 3.x tiered setup."""
    settings = Settings(_env_file=None)
    assert settings.gemini_fast_model == "gemini-3.5-flash-lite"
    assert settings.gemini_complex_model == "gemini-3.8-flash"
    assert settings.fallback_model_list == ["gemini-3.1-flash-lite"]
    assert settings.auth_mode == "token"


def test_comma_separated_list_properties() -> None:
    """Fallback models and CORS origins strip whitespace and empty items."""
    settings = Settings(
        _env_file=None,
        gemini_fallback_models=" gemini-3.1-flash-lite , , gemini-3.5-flash-lite ",
        cors_origins="http://localhost:3000, https://demo.example.com , ",
    )
    assert settings.fallback_model_list == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    assert settings.cors_origin_list == ["http://localhost:3000", "https://demo.example.com"]


def test_settings_numeric_and_auth_bounds() -> None:
    """Invalid thresholds or unknown auth modes fail Pydantic validation."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, hitl_confidence_threshold=1.5)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_retry_attempts=0)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_mode="invalid_mode")  # type: ignore[arg-type]
