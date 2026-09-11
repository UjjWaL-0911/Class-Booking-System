"""Database layer tests.

These run against real PostgreSQL. That is not incidental: `FOR UPDATE`, GiST
exclusion constraints, deferrable constraint triggers and `tstzrange` have no
SQLite equivalent, and they are most of what makes this system worth testing.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import build_engine, build_session_factory
from app.db.transaction import apply_local_timeouts, guarded_transaction
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture
async def db() -> AsyncSession:
    engine = build_engine(url=TEST_DATABASE_URL)
    factory = build_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


class TestEngine:
    async def test_connects_to_postgres(self, db: AsyncSession) -> None:
        version = (await db.execute(text("SELECT version()"))).scalar_one()
        assert "PostgreSQL" in version

    async def test_url_disables_the_dialect_statement_cache(self) -> None:
        """Half of the transaction-pooler fix. The other half is in connect_args.

        Passing this as a create_async_engine keyword raises TypeError — it is a
        dialect option read off the URL — which is why it is asserted here.
        """
        engine = build_engine(url=TEST_DATABASE_URL)
        assert engine.url.query["prepared_statement_cache_size"] == "0"
        await engine.dispose()

    async def test_plain_postgresql_url_is_normalised_to_asyncpg(self) -> None:
        engine = build_engine(url="postgresql://u:p@localhost:5432/db")
        assert engine.url.drivername == "postgresql+asyncpg"
        await engine.dispose()

    async def test_prepared_statements_do_not_accumulate(self, db: AsyncSession) -> None:
        """Through a transaction pooler, cached prepared statements surface as
        intermittent DuplicatePreparedStatementError once a server connection is
        reassigned. The count staying flat is the evidence that cannot happen."""
        for i in range(20):
            await db.execute(text("SELECT :n ::int + 1"), {"n": i})
        first = (await db.execute(text("SELECT count(*) FROM pg_prepared_statements"))).scalar_one()

        for i in range(200):
            await db.execute(text("SELECT :n ::int + 2"), {"n": i})
        second = (
            await db.execute(text("SELECT count(*) FROM pg_prepared_statements"))
        ).scalar_one()

        # Only the counting statement itself is ever in flight.
        assert first == second == 1


class TestTransactionGuards:
    async def test_timeouts_are_applied_to_the_transaction(self, db: AsyncSession) -> None:
        async with guarded_transaction(db):
            lock_timeout = (await db.execute(text("SHOW lock_timeout"))).scalar_one()
            statement_timeout = (await db.execute(text("SHOW statement_timeout"))).scalar_one()

        assert lock_timeout == "3s"
        assert statement_timeout == "10s"

    async def test_timeouts_do_not_leak_past_the_transaction(self, db: AsyncSession) -> None:
        """The reason for SET LOCAL rather than SET.

        Under a transaction pooler the server connection goes to a different client
        the moment this transaction ends. A bare SET would silently apply our
        timeouts to that client's unrelated work.
        """
        async with guarded_transaction(db):
            await db.execute(text("SELECT 1"))

        after = (await db.execute(text("SHOW lock_timeout"))).scalar_one()
        assert after == "0"  # server default: no timeout

    async def test_transaction_rolls_back_on_error(self, db: AsyncSession) -> None:
        await db.execute(text("CREATE TEMP TABLE rollback_probe (id int PRIMARY KEY)"))
        await db.commit()

        with pytest.raises(RuntimeError):
            async with guarded_transaction(db):
                await db.execute(text("INSERT INTO rollback_probe VALUES (1)"))
                raise RuntimeError("boom")

        count = (await db.execute(text("SELECT count(*) FROM rollback_probe"))).scalar_one()
        assert count == 0

    async def test_apply_local_timeouts_requires_a_transaction_to_be_useful(
        self, db: AsyncSession
    ) -> None:
        """Outside an explicit transaction SQLAlchemy autobegins one, so SET LOCAL
        still applies — the assertion documents that this is understood rather
        than accidental."""
        await apply_local_timeouts(db)
        assert (await db.execute(text("SHOW lock_timeout"))).scalar_one() == "3s"
        await db.rollback()


class TestReadinessProbe:
    async def test_ready_reports_the_database_is_reachable(self, client: AsyncClient) -> None:
        response = await client.get("/health/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "reachable"

    async def test_liveness_does_not_touch_the_database(self, client: AsyncClient) -> None:
        """Liveness must stay cheap — Render polls it frequently. The keep-warm
        cron uses /health/ready precisely because this one proves nothing about
        Supabase being awake."""
        response = await client.get("/health")

        assert response.status_code == 200
        assert "database" not in response.json()

    async def test_ready_reports_503_when_the_database_is_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken deployment must fail its health check, not pass with a note in
        the body — otherwise Render would happily route traffic to it."""
        from httpx import ASGITransport
        from httpx import AsyncClient as Client

        from app.core.config import get_settings
        from app.db import engine as engine_module
        from app.main import create_app

        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+asyncpg://nobody:wrong@localhost:5432/does_not_exist",
        )
        get_settings.cache_clear()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()

        transport = ASGITransport(app=create_app())
        async with Client(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json()["status"] == "unavailable"
        assert response.json()["database"] == "unreachable"
