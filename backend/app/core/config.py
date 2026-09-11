"""Application configuration.

Every value arrives from the environment. Nothing here has a default that would be
wrong-but-plausible in production: a missing secret must crash the process at start-up
rather than surface as a 500 an hour later.

`STUDIO_TIMEZONE` deserves special mention — four of the ten goals ("sessions today",
"no-shows this week", the seven-day alert window, and the "has this session started"
settlement gate) silently produce wrong numbers if it falls back to UTC, so it is
required and validated against the IANA database at start-up.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_core.core_schema import ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Where this process is running. Drives log format and docs exposure."""

    LOCAL = "local"
    CI = "ci"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ app
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ------------------------------------------------------------- database
    # Application connection: transaction-mode pooler, least-privilege role.
    # Both prepared-statement caches are disabled in the engine, not here.
    database_url: str

    # Alembic only: session-mode pooler, owner role. DDL and transaction
    # pooling do not mix, so migrations never use `database_url`.
    migration_database_url: str

    db_pool_size: int = 5
    db_max_overflow: int = 5
    # Must stay below the pooler's own idle timeout, or the first request after
    # a Render sleep gets a dead connection.
    db_pool_recycle_seconds: int = 300
    db_echo: bool = False

    # Applied with SET LOCAL inside each transaction, never as a bare SET:
    # a plain SET would leak onto the pooled server connection.
    lock_timeout_ms: int = 3_000
    statement_timeout_ms: int = 10_000

    # ------------------------------------------------------------------ auth
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    # A token rotated within this window may be presented again and re-issues the
    # existing successor, so a refresh race cannot log the user out. Reuse detection
    # is deliberately off inside it — see architecture.md.
    refresh_grace_seconds: int = 10
    refresh_cookie_name: str = "cbs_refresh"

    # OWASP baseline, not the argon2-cffi default of 64 MiB: concurrent logins at
    # 64 MiB each are an out-of-memory kill on a 512 MB instance.
    argon2_memory_cost_kib: int = 19_456
    argon2_time_cost: int = 2
    argon2_parallelism: int = 1
    # Hashing runs in a threadpool; capped well below Starlette's default of 40
    # for the same memory reason.
    hashing_threadpool_size: int = 4

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60

    # ---------------------------------------------------------------- proxy
    # The SPA's static host rewrites /api/* to this service, so request.client.host
    # is always the proxy. Anything reasoning about the caller's address reads
    # X-Forwarded-For and skips this many trailing hops.
    trusted_proxy_hops: int = 1

    # ------------------------------------------------------------- business
    studio_timezone: str
    membership_alert_window_days: int = 7
    # Bounded because each generated occurrence takes a SAVEPOINT, and Postgres
    # caches only 64 subtransaction ids per backend before a performance cliff.
    max_recurrence_candidates: int = 200

    # -------------------------------------------------------- observability
    sentry_dsn: str | None = None

    # ------------------------------------------------------------ validation
    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _must_be_postgres(cls, value: str, info: ValidationInfo) -> str:
        if not value.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError(
                f"{info.field_name} must be a PostgreSQL URL "
                f"(postgresql:// or postgresql+asyncpg://)"
            )
        return value

    @field_validator("studio_timezone")
    @classmethod
    def _must_be_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"STUDIO_TIMEZONE={value!r} is not a valid IANA timezone "
                f"(for example: Asia/Kolkata, Europe/London)"
            ) from exc
        return value

    @field_validator("log_level")
    @classmethod
    def _must_be_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return upper

    # -------------------------------------------------------------- helpers
    @property
    def tz(self) -> ZoneInfo:
        """The studio's timezone, for every date-bucketed query."""
        return ZoneInfo(self.studio_timezone)

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def docs_url(self) -> str | None:
        """OpenAPI docs are served everywhere except production."""
        return None if self.is_production else "/docs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor. Used as a FastAPI dependency and at import time.

    The cache is what lets tests override configuration by clearing it, rather
    than by mutating a module-level global.
    """
    # Required fields are supplied by the environment, which mypy cannot see.
    return Settings()
