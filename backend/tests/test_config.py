"""Configuration tests.

The point of these is not that pydantic works — it is that the *specific*
guardrails we added work, because each one exists to stop a failure that would
otherwise be silent in production.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings, get_settings


def test_settings_load_from_environment() -> None:
    settings = get_settings()
    assert settings.environment is Environment.CI
    assert settings.studio_timezone == "Asia/Kolkata"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_secret_is_not_exposed_by_repr() -> None:
    """A SecretStr keeps the signing key out of logs and tracebacks."""
    settings = get_settings()
    assert "test-secret" not in repr(settings)
    assert settings.jwt_secret.get_secret_value() == TEST_SECRET


def test_tz_property_returns_a_usable_zone() -> None:
    from datetime import datetime

    settings = get_settings()
    # Asia/Kolkata is UTC+5:30 year-round — a good canary for a tz database that
    # loaded but is empty, which would silently give UTC.
    offset = datetime(2026, 1, 1, 12, 0, tzinfo=settings.tz).utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 5.5 * 3600


class TestValidation:
    """Each of these would be a silent production bug if it were not rejected."""

    def test_unknown_timezone_is_rejected(self, clean_env: pytest.MonkeyPatch) -> None:
        clean_env.setenv("STUDIO_TIMEZONE", "Mars/Olympus_Mons")
        _set_required(clean_env, skip="STUDIO_TIMEZONE")

        with pytest.raises(ValidationError, match="not a valid IANA timezone"):
            Settings()

    def test_missing_timezone_is_rejected(self, clean_env: pytest.MonkeyPatch) -> None:
        """No default: four goals silently produce wrong numbers under UTC."""
        _set_required(clean_env, skip="STUDIO_TIMEZONE")

        with pytest.raises(ValidationError, match="studio_timezone"):
            Settings()

    def test_missing_jwt_secret_is_rejected(self, clean_env: pytest.MonkeyPatch) -> None:
        """A missing secret must crash the deploy, not surface as a 500 later."""
        _set_required(clean_env, skip="JWT_SECRET")

        with pytest.raises(ValidationError, match="jwt_secret"):
            Settings()

    def test_non_postgres_url_is_rejected(self, clean_env: pytest.MonkeyPatch) -> None:
        """Guards against pointing the app at SQLite, where none of the
        concurrency machinery (FOR UPDATE, GiST, deferred triggers) exists."""
        _set_required(clean_env, skip="DATABASE_URL")
        clean_env.setenv("DATABASE_URL", "sqlite+aiosqlite:///./local.db")

        with pytest.raises(ValidationError, match="must be a PostgreSQL URL"):
            Settings()

    def test_invalid_log_level_is_rejected(self, clean_env: pytest.MonkeyPatch) -> None:
        _set_required(clean_env)
        clean_env.setenv("LOG_LEVEL", "CHATTY")

        with pytest.raises(ValidationError, match="LOG_LEVEL must be one of"):
            Settings()

    def test_log_level_is_normalised_to_upper_case(self, clean_env: pytest.MonkeyPatch) -> None:
        _set_required(clean_env)
        clean_env.setenv("LOG_LEVEL", "debug")

        assert Settings().log_level == "DEBUG"


class TestProductionBehaviour:
    def test_docs_are_hidden_in_production(self, clean_env: pytest.MonkeyPatch) -> None:
        _set_required(clean_env)
        clean_env.setenv("ENVIRONMENT", "production")

        settings = Settings()
        assert settings.is_production is True
        assert settings.docs_url is None

    def test_docs_are_available_locally(self) -> None:
        assert get_settings().docs_url == "/docs"


# --------------------------------------------------------------------------- helpers

TEST_SECRET = "test-secret-not-used-in-any-real-deployment"

_REQUIRED = {
    "DATABASE_URL": "postgresql+asyncpg://postgres:pw@localhost:5432/db",
    "MIGRATION_DATABASE_URL": "postgresql://postgres:pw@localhost:5432/db",
    "JWT_SECRET": TEST_SECRET,
    "STUDIO_TIMEZONE": "Asia/Kolkata",
}


def _set_required(mp: pytest.MonkeyPatch, skip: str | None = None) -> None:
    """Set every required variable except one, so a test can assert on its absence."""
    for key, value in _REQUIRED.items():
        if key != skip:
            mp.setenv(key, value)
