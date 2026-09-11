"""Transaction helpers.

Every write path in this system runs inside ``guarded_transaction``. It exists for
one reason: to make sure the per-transaction timeouts are applied with ``SET LOCAL``
and never with a bare ``SET``.

The distinction is not cosmetic. Through a transaction-mode pooler the server
connection is handed to a different client the moment the transaction ends, so a
plain ``SET lock_timeout`` would silently apply to somebody else's unrelated work.
``SET LOCAL`` is scoped to the transaction and reverts on commit or rollback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings


async def apply_local_timeouts(session: AsyncSession, settings: Settings | None = None) -> None:
    """Apply ``lock_timeout`` and ``statement_timeout`` to the current transaction.

    ``SET`` does not accept bind parameters, so the values are interpolated. They
    are ``int`` fields on the settings model and coerced again here, which is what
    makes that safe.
    """
    settings = settings or get_settings()
    lock_ms = int(settings.lock_timeout_ms)
    statement_ms = int(settings.statement_timeout_ms)
    await session.execute(text(f"SET LOCAL lock_timeout = '{lock_ms}ms'"))
    await session.execute(text(f"SET LOCAL statement_timeout = '{statement_ms}ms'"))


@asynccontextmanager
async def guarded_transaction(
    session: AsyncSession, settings: Settings | None = None
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with the timeouts applied.

    Commits on success, rolls back on any exception. A contender that waits longer
    than ``lock_timeout`` gets a clean, retryable error instead of pinning a worker
    for the length of someone else's transaction.

    Usage::

        async with guarded_transaction(session):
            booking = await booking_service.cancel(...)
    """
    settings = settings or get_settings()
    async with session.begin():
        await apply_local_timeouts(session, settings)
        yield session


async def lock_session_row(session: AsyncSession, session_id: object) -> None:
    """Take the per-session write lock that serialises every capacity decision.

    Deliberately a named helper rather than an inline ``SELECT``: this lock is the
    single most important invariant in the system, and it should be greppable.
    Callers must already be inside a transaction.
    """
    await session.execute(
        text("SELECT 1 FROM sessions WHERE id = :sid FOR UPDATE"),
        {"sid": session_id},
    )
