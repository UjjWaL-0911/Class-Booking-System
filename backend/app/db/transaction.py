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

    **One statement, not two, and that is a latency fix rather than a tidy-up.**
    These two lines used to be two ``SET LOCAL`` statements, which is two network
    round trips on the critical path of every single request. Against a database
    in another region that was 205ms of the ~600ms a trivial request cost — more
    than the query it was protecting.

    ``set_config(key, value, is_local => true)`` is exactly ``SET LOCAL``: scoped
    to the transaction, reverted on commit or rollback, and therefore still safe
    through a transaction-mode pooler that hands the server connection to somebody
    else the moment this transaction ends. The difference is that two of them fit
    in one ``SELECT``, so the round trip is paid once.

    ``set_config`` also takes bind parameters, which ``SET`` does not — so the
    values stop being interpolated into SQL. They were only ever ``int`` fields
    coerced again here, but a parameter is a better argument than a promise.
    """
    settings = settings or get_settings()
    await session.execute(
        text(
            "SELECT set_config('lock_timeout', :lock, true), "
            "set_config('statement_timeout', :statement, true)"
        ),
        {
            "lock": f"{int(settings.lock_timeout_ms)}ms",
            "statement": f"{int(settings.statement_timeout_ms)}ms",
        },
    )


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
