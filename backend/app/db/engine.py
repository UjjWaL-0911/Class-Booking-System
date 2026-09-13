"""Async engine and session factory.

Most of this file is pooler compatibility, and each setting exists because of a
specific failure mode rather than as general tuning. The application talks to
Supabase through Supavisor in **transaction** mode, which multiplexes many clients
onto a few real Postgres connections — cheap on a free tier, and constraining in
ways that do not show up when developing against a local Postgres directly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings


def _as_asyncpg_url(url: str) -> URL:
    """Normalise onto the asyncpg driver and disable its prepared-statement cache.

    Config accepts both ``postgresql://`` and ``postgresql+asyncpg://`` so a value
    can be pasted straight from Supabase, but the async engine needs the driver
    named explicitly.

    ``prepared_statement_cache_size`` is set here rather than passed to
    ``create_async_engine``: it is a *dialect* option that the asyncpg dialect reads
    off the URL query string, and passing it as an engine keyword raises
    ``TypeError: Invalid argument(s) 'prepared_statement_cache_size'``. It is the
    second of the two caches that a transaction pooler requires be turned off —
    the other is asyncpg's own, in ``connect_args`` below.
    """
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+asyncpg")
    if "prepared_statement_cache_size" not in parsed.query:
        parsed = parsed.update_query_dict({"prepared_statement_cache_size": "0"})
    return parsed


def build_engine(
    settings: Settings | None = None,
    *,
    url: str | None = None,
    **overrides: Any,
) -> AsyncEngine:
    """Create an engine configured for the Supabase transaction pooler.

    ``url`` and ``overrides`` exist for tests: the concurrency suite needs more
    simultaneous connections than the production pool allows, because twenty
    parallel bookings genuinely require twenty connections.
    """
    settings = settings or get_settings()

    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        # `pool_pre_ping` is deliberately OFF, and `pool_recycle` is what replaces
        # it. Pre-ping validates the connection with a round trip before handing it
        # out — on every request, on the critical path. Measured against Supabase
        # from another region that was 35% of the cost of a whole trivial request,
        # which is a large toll to pay continuously to insure against a rare event.
        #
        # What it was insuring against is mostly not a risk here. Render stops the
        # container when it sleeps, so waking starts a fresh process with an empty
        # pool and no stale sockets to trip over. The remaining case is a
        # connection the pooler drops while this process stays alive — and
        # `pool_recycle` already discards anything older than five minutes, which
        # is shorter than the pooler's own idle timeout.
        #
        # If dead connections ever do surface, the fix is a retry on the specific
        # disconnect error rather than a ping before every query: pay on the rare
        # failure instead of on every success.
        "pool_pre_ping": False,
        "pool_recycle": settings.db_pool_recycle_seconds,
        "connect_args": {
            # asyncpg's cache. Prepared statements do not survive a transaction
            # pooler handing the connection to someone else.
            "statement_cache_size": 0,
            # Even uncached, asyncpg names each prepared statement. Unique names
            # stop a collision when two clients share one server connection.
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        },
    }
    kwargs.update(overrides)

    return create_async_engine(_as_asyncpg_url(url or settings.database_url), **kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        # Attributes stay loaded after commit, so a service can return an object it
        # just wrote without triggering a lazy refresh outside the transaction.
        expire_on_commit=False,
        autoflush=False,
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """The process-wide engine. Cached so the pool is created exactly once."""
    return build_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return build_session_factory(get_engine())


async def dispose_engine() -> None:
    """Close every pooled connection. Called on application shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session and always close it.

    Deliberately does not open a transaction: services own their own transaction
    boundaries, because where a transaction starts and ends is a domain decision
    in this system, not a request-lifecycle detail.
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session
