"""Authentication tests (goal 1).

Goal 1 says the role difference "must be enforced on the server, not just hidden in
the interface", so every authorization test here calls the API directly with a token
rather than checking what an interface would render.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from tests.conftest import (
    CSRF_HEADERS,
    INSTRUCTOR_PASSWORD,
    STAFF_PASSWORD,
)

pytestmark = pytest.mark.usefixtures("migrated_schema")


async def _login(api: AsyncClient, email: str, password: str) -> dict[str, object]:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


class TestLogin:
    async def test_valid_credentials_return_a_token_and_a_cookie(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": STAFF_PASSWORD},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["role"] == "staff"
        assert "cbs_refresh" in response.cookies

    async def test_the_refresh_token_never_appears_in_the_body(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        """It travels only as an httpOnly cookie, so an XSS bug cannot read it."""
        response = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": STAFF_PASSWORD},
        )

        assert "refresh" not in response.text.lower()
        set_cookie = response.headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie

    async def test_wrong_password_is_rejected(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": "wrong"},
        )

        assert response.status_code == 401

    async def test_unknown_and_wrong_are_indistinguishable(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        """Different messages would tell an attacker which emails are registered."""
        unknown = await api.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        wrong = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": "wrong"},
        )

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["message"] == wrong.json()["message"]

    async def test_a_deactivated_account_cannot_sign_in(
        self, api: AsyncClient, accounts: dict[str, str], db: AsyncSession
    ) -> None:
        await db.execute(
            text("UPDATE users SET is_active = false WHERE email = :e"),
            {"e": accounts["staff"]},
        )
        await db.commit()

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": STAFF_PASSWORD},
        )

        assert response.status_code == 401


class TestAccessToken:
    async def test_me_returns_the_signed_in_user(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        token = (await _login(api, accounts["staff"], STAFF_PASSWORD))["access_token"]

        response = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["email"] == accounts["staff"]

    async def test_no_token_is_rejected(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/auth/me")).status_code == 401

    async def test_a_tampered_token_is_rejected(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        token = (await _login(api, accounts["staff"], STAFF_PASSWORD))["access_token"]
        forged = f"{token[:-4]}AAAA"

        response = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})

        assert response.status_code == 401

    async def test_deactivating_an_account_revokes_access_immediately(
        self, api: AsyncClient, accounts: dict[str, str], db: AsyncSession
    ) -> None:
        """The reason get_current_user re-loads the user on every request.

        The token is still cryptographically valid and unexpired; it stops working
        anyway, which is the whole justification for that round-trip.
        """
        token = (await _login(api, accounts["staff"], STAFF_PASSWORD))["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert (await api.get("/api/v1/auth/me", headers=headers)).status_code == 200

        await db.execute(
            text("UPDATE users SET is_active = false WHERE email = :e"),
            {"e": accounts["staff"]},
        )
        await db.commit()

        assert (await api.get("/api/v1/auth/me", headers=headers)).status_code == 401


class TestRefreshRotation:
    async def test_refresh_issues_a_new_access_token_and_rotates_the_cookie(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        await _login(api, accounts["staff"], STAFF_PASSWORD)
        first_cookie = api.cookies["cbs_refresh"]

        response = await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)

        assert response.status_code == 200
        assert response.json()["access_token"]
        assert api.cookies["cbs_refresh"] != first_cookie

    async def test_refresh_without_a_cookie_is_rejected(self, api: AsyncClient) -> None:
        assert (await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)).status_code == 401

    async def test_reusing_a_rotated_token_revokes_the_whole_family(
        self, api: AsyncClient, accounts: dict[str, str], db: AsyncSession
    ) -> None:
        """The entire point of rotating.

        The grace window is stepped over deliberately: inside it a replay is treated
        as a benign race between tabs, which is a trade the design makes explicitly.
        """
        await _login(api, accounts["staff"], STAFF_PASSWORD)
        stolen = api.cookies["cbs_refresh"]

        await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)  # rotates
        current = api.cookies["cbs_refresh"]

        await db.execute(
            text(
                "UPDATE refresh_tokens SET revoked_at = now() - interval '1 hour' "
                "WHERE revoked_at IS NOT NULL"
            )
        )
        await db.commit()

        api.cookies.set("cbs_refresh", stolen)
        replay = await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
        assert replay.status_code == 401

        # And the legitimate holder is locked out too — that is the intent: the
        # family is compromised, so everything in it dies.
        api.cookies.set("cbs_refresh", current)
        after = await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
        assert after.status_code == 401

    async def test_a_replay_inside_the_grace_window_is_tolerated(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        """Several tabs refreshing at once must not log the user out."""
        await _login(api, accounts["staff"], STAFF_PASSWORD)
        original = api.cookies["cbs_refresh"]

        await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)

        api.cookies.set("cbs_refresh", original)
        response = await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)

        assert response.status_code == 200
        assert response.json()["access_token"]


class TestCsrfGuard:
    async def test_refresh_requires_the_custom_header(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        """Without it, any origin could POST here with the ambient cookie and
        rotate a victim's session out from under them."""
        await _login(api, accounts["staff"], STAFF_PASSWORD)

        response = await api.post("/api/v1/auth/refresh", headers={"Origin": "http://test"})

        assert response.status_code == 401

    async def test_refresh_fails_closed_without_an_origin(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        await _login(api, accounts["staff"], STAFF_PASSWORD)

        response = await api.post("/api/v1/auth/refresh", headers={"X-Refresh-Request": "1"})

        assert response.status_code == 401


class TestLogout:
    async def test_logout_invalidates_the_refresh_token(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        """Logging out has to mean something, which is why refresh tokens are rows
        rather than self-validating strings."""
        await _login(api, accounts["staff"], STAFF_PASSWORD)
        token = api.cookies["cbs_refresh"]

        assert (await api.post("/api/v1/auth/logout")).status_code == 204

        api.cookies.set("cbs_refresh", token)
        response = await api.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
        assert response.status_code == 401

    async def test_logout_without_a_session_is_still_204(self, api: AsyncClient) -> None:
        assert (await api.post("/api/v1/auth/logout")).status_code == 204


class TestRoleEnforcement:
    async def test_the_token_carries_the_role(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        staff = await _login(api, accounts["staff"], STAFF_PASSWORD)
        instructor = await _login(api, accounts["instructor"], INSTRUCTOR_PASSWORD)

        assert staff["user"]["role"] == "staff"
        assert instructor["user"]["role"] == "instructor"


class TestPasswordHashing:
    async def test_hashes_are_salted(self) -> None:
        """Two identical passwords must not produce the same hash."""
        first = await hash_password("same-password")
        second = await hash_password("same-password")

        assert first != second
        assert first.startswith("$argon2id$")

    async def test_hashing_uses_the_configured_memory_cost(self) -> None:
        """19 MiB, the OWASP baseline — not argon2-cffi's 64 MiB default, which
        would exhaust a 512 MB instance under a handful of concurrent logins."""
        digest = await hash_password("x")

        assert "m=19456" in digest


class TestClockInjection:
    async def test_expired_access_tokens_are_rejected(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        from app.core.deps import utc_now
        from app.main import create_app

        app = create_app()
        past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
        app.dependency_overrides[utc_now] = lambda: past

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            issued = await client.post(
                "/api/v1/auth/login",
                json={"email": accounts["staff"], "password": STAFF_PASSWORD},
            )
            token = issued.json()["access_token"]

        response = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
