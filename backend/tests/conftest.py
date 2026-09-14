"""Shared test fixtures.

Configuration is read from the environment like everywhere else, but tests set
their own values here so a developer's local `.env` can never change a test's
outcome. `get_settings` is `lru_cache`d, so clearing the cache is what makes an
override take effect — that is the reason it is a cached function rather than a
module-level global.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# The test database is real PostgreSQL, never SQLite: FOR UPDATE, GiST exclusion
# constraints, deferrable constraint triggers and tstzrange have no SQLite equivalent,
# and they are most of what makes this system worth testing.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://cbs_owner:ig8770gm_y9FqkCfOh9_iOyM@localhost:5432/class_booking_test",
)

TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "ci",
    "LOG_LEVEL": "WARNING",
    "DATABASE_URL": TEST_DATABASE_URL,
    "MIGRATION_DATABASE_URL": TEST_DATABASE_URL.replace("+asyncpg", ""),
    "JWT_SECRET": "test-secret-not-used-in-any-real-deployment",
    "STUDIO_TIMEZONE": "Asia/Kolkata",
}


def _clear_caches() -> None:
    """Reset every process-wide cache so a test cannot inherit another's config."""
    from app.core.config import get_settings
    from app.core.deps import get_login_rate_limiter
    from app.db.engine import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    # The limiter's counters *are* its state, so a shared instance would make
    # tests fail depending on how many logged in before them.
    get_login_rate_limiter.cache_clear()


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin configuration for every test, and reset the cache around each one."""
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    # Ignore any .env sitting in the working directory.
    monkeypatch.setattr("app.core.config.Settings.model_config", {"extra": "ignore"})

    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight to the ASGI app — no network, no server."""
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Strip every application variable, for tests that assert on missing config."""
    for key in list(os.environ):
        if key in TEST_ENV:
            monkeypatch.delenv(key, raising=False)
    _clear_caches()
    yield monkeypatch
    _clear_caches()


@pytest.fixture(scope="session")
def migrated_schema() -> None:
    """Bring the test database to head before any schema test runs.

    Session-scoped and idempotent: `alembic upgrade head` is a no-op once applied,
    so this costs one connection per test session rather than per test.
    """
    from alembic.config import Config

    from alembic import command

    for key, value in TEST_ENV.items():
        os.environ.setdefault(key, value)
    os.environ["MIGRATION_DATABASE_URL"] = TEST_DATABASE_URL.replace("+asyncpg", "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")
    get_settings.cache_clear()


# --------------------------------------------------------------- shared fixtures
#
# Everything below exists so a component's tests are about that component. Signing
# in is not the subject of the class or booking tests, so it happens once here.

STAFF_PASSWORD = "correct-horse-battery-staple"
INSTRUCTOR_PASSWORD = "another-perfectly-fine-password"

# Browsers always send Origin on a cross-document POST, and /auth/refresh
# additionally requires a non-simple header that a foreign origin cannot set
# without passing a preflight.
CSRF_HEADERS = {"X-Refresh-Request": "1", "Origin": "http://test"}


@pytest.fixture
async def db(migrated_schema: None) -> AsyncIterator[AsyncSession]:
    """A session against the migrated test database."""
    from app.db.engine import build_engine, build_session_factory

    engine = build_engine(url=TEST_DATABASE_URL)
    factory = build_session_factory(engine)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def api(migrated_schema: None) -> AsyncIterator[AsyncClient]:
    """An unauthenticated client against a freshly built app."""
    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def accounts(db: AsyncSession) -> dict[str, str]:
    """One staff account and one instructor account, with unique emails.

    Emails are tagged per test so the suite can run without truncating tables
    between cases — which matters because `booking_events` cannot be truncated at
    all, by design.
    """
    import uuid

    from sqlalchemy import text

    from app.core.security import hash_password

    tag = uuid.uuid4().hex[:8]
    emails = {
        "staff": f"staff-{tag}@example.com",
        "instructor": f"inst-{tag}@example.com",
    }
    for role, password in (
        ("staff", STAFF_PASSWORD),
        ("instructor", INSTRUCTOR_PASSWORD),
    ):
        await db.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name, role) "
                "VALUES (:e, :h, :n, CAST(:r AS user_role))"
            ),
            {
                "e": emails[role],
                "h": await hash_password(password),
                "n": role.title(),
                "r": role,
            },
        )
    await db.commit()
    return emails


async def _authenticate(client: AsyncClient, email: str, password: str) -> AsyncClient:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def staff(api: AsyncClient, accounts: dict[str, str]) -> AsyncClient:
    """A client signed in as studio staff."""
    return await _authenticate(api, accounts["staff"], STAFF_PASSWORD)


MEMBER_PASSWORD = "a-perfectly-ordinary-member-password"


@pytest.fixture
async def member_account(staff: AsyncClient) -> dict[str, str]:
    """A member with a login, created the only way one can be: by staff.

    Returns the member record plus the password, because a test that signs in as
    this person needs both and looking the password up from a constant at each
    call site is how they drift.
    """
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:8]
    created = await staff.post(
        "/api/v1/members",
        json={
            "full_name": f"Member {tag}",
            "email": f"member-{tag}@example.com",
            # Comfortably in the future: the expiry rule is goal 4's and has its
            # own tests. A fixture that quietly expires would make unrelated
            # member tests fail for a reason that is not their subject.
            "membership_expiry": "2030-01-01",
            "notes": "",
        },
    )
    assert created.status_code == 201, created.text
    record = dict(created.json())

    enabled = await staff.post(
        f"/api/v1/members/{record['id']}/account", json={"password": MEMBER_PASSWORD}
    )
    assert enabled.status_code == 201, enabled.text
    return {"id": record["id"], "email": record["email"], "password": MEMBER_PASSWORD}


@pytest.fixture
async def member(
    migrated_schema: None, member_account: dict[str, str]
) -> AsyncIterator[AsyncClient]:
    """A client signed in as a member.

    Its own client, like the instructor fixture, so a test can hold a staff
    session and a member session at once — which every authorization test here
    needs, because the question is always "what can this one see that that one
    can".
    """
    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield await _authenticate(client, member_account["email"], member_account["password"])


@pytest.fixture
async def instructor(migrated_schema: None, accounts: dict[str, str]) -> AsyncIterator[AsyncClient]:
    """A client signed in as an instructor.

    Its own client instance, so a test can hold a staff session and an instructor
    session at the same time — which is what the authorization tests need.
    """
    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield await _authenticate(client, accounts["instructor"], INSTRUCTOR_PASSWORD)
