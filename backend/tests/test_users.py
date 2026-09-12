"""The people who can sign in: listing them, and adding one.

For the list, three things worth proving: it is staff only (goal 1's rule is
enforced on the server, not hidden in the interface), it includes staff accounts
as well as instructors — because that is the rule the session service applies when
it validates an instructor id — and it leaves out deactivated accounts, so a
picker can never offer somebody the server would then refuse.

For creation, the thing worth proving is that it is not a registration endpoint.
An instructor cannot use it, so nobody can promote themselves; the password never
comes back out in any form; and the account it makes is a real one that can sign in
and is immediately schedulable. That last case is the reason this endpoint exists —
an instructor who cannot be put in front of a class is not an instructor.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")


class TestListUsers:
    async def test_staff_see_both_roles(self, staff: AsyncClient, accounts: dict[str, str]) -> None:
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200, response.text
        by_email = {row["email"]: row for row in response.json()}
        # Both appear: any active user may lead a session, so a picker that showed
        # only role='instructor' would disagree with what the server accepts.
        assert accounts["staff"] in by_email
        assert accounts["instructor"] in by_email
        assert by_email[accounts["staff"]]["role"] == "staff"
        assert by_email[accounts["instructor"]]["role"] == "instructor"

    async def test_no_password_hash_is_returned(self, staff: AsyncClient) -> None:
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        for row in response.json():
            assert set(row) == {"id", "email", "full_name", "role"}

    async def test_deactivated_accounts_are_left_out(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        await db.execute(
            text("UPDATE users SET is_active = false WHERE email = :e"),
            {"e": accounts["instructor"]},
        )
        await db.commit()

        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        emails = [row["email"] for row in response.json()]
        assert accounts["instructor"] not in emails

    async def test_sorted_by_name(self, staff: AsyncClient) -> None:
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        names = [row["full_name"] for row in response.json()]
        assert names == sorted(names)

    async def test_instructors_are_refused(self, instructor: AsyncClient) -> None:
        response = await instructor.get("/api/v1/users")

        assert response.status_code == 403, response.text

    async def test_signing_in_is_required(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/users")

        assert response.status_code == 401, response.text


def _person(**overrides: object) -> dict[str, object]:
    tag = uuid.uuid4().hex[:8]
    return {
        "email": f"new-{tag}@studio.demo",
        "full_name": f"New Person {tag}",
        "role": "instructor",
        "password": "a-long-enough-password",
        **overrides,
    }


class TestCreateUser:
    async def test_staff_can_add_an_instructor(self, staff: AsyncClient) -> None:
        body = _person()

        response = await staff.post("/api/v1/users", json=body)

        assert response.status_code == 201, response.text
        created = response.json()
        assert created["email"] == body["email"]
        assert created["role"] == "instructor"
        # The response shape is the same one sign-in returns, which is how it
        # carries neither the password nor its hash.
        assert set(created) == {"id", "email", "full_name", "role"}

    async def test_staff_can_add_another_member_of_staff(self, staff: AsyncClient) -> None:
        response = await staff.post("/api/v1/users", json=_person(role="staff"))

        assert response.status_code == 201, response.text
        assert response.json()["role"] == "staff"

    async def test_the_new_account_can_sign_in(self, staff: AsyncClient, api: AsyncClient) -> None:
        """The account is real, not a row that looks like one."""
        body = _person()
        await staff.post("/api/v1/users", json=body)

        signed_in = await api.post(
            "/api/v1/auth/login",
            json={"email": body["email"], "password": body["password"]},
        )

        assert signed_in.status_code == 200, signed_in.text
        assert signed_in.json()["user"]["email"] == body["email"]

    async def test_a_new_instructor_can_be_put_in_front_of_a_class(
        self, staff: AsyncClient
    ) -> None:
        """The whole point of the endpoint. Goals 3, 5 and 7 take an instructor by
        id, so an account that cannot be selected as one has solved nothing."""
        created = (await staff.post("/api/v1/users", json=_person())).json()

        listed = (await staff.get("/api/v1/users")).json()

        assert created["id"] in {row["id"] for row in listed}

    async def test_an_instructor_cannot_add_anybody(self, instructor: AsyncClient) -> None:
        """Otherwise the endpoint is self-registration with extra steps: anybody
        with an account could mint a staff one and goal 1's enforcement would be
        decorative."""
        response = await instructor.post("/api/v1/users", json=_person(role="staff"))

        assert response.status_code == 403

    async def test_anonymous_callers_are_refused(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/users", json=_person())

        assert response.status_code == 401

    async def test_a_duplicate_address_is_a_clean_conflict(self, staff: AsyncClient) -> None:
        body = _person()
        assert (await staff.post("/api/v1/users", json=body)).status_code == 201

        again = await staff.post("/api/v1/users", json=body)

        assert again.status_code == 409
        assert "already exists" in again.json()["message"]

    async def test_the_address_is_case_insensitive(self, staff: AsyncClient) -> None:
        """`users.email` is citext, so Ada@ and ada@ are one person. Without that
        the uniqueness constraint would be close to useless."""
        body = _person()
        assert (await staff.post("/api/v1/users", json=body)).status_code == 201

        shouted = await staff.post("/api/v1/users", json=_person(email=str(body["email"]).upper()))

        assert shouted.status_code == 409

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("email", "not-an-address"),
            ("full_name", ""),
            ("role", "owner"),
            ("password", "short"),
        ],
    )
    async def test_bad_input_is_refused(
        self, staff: AsyncClient, field: str, value: str
    ) -> None:
        response = await staff.post("/api/v1/users", json=_person(**{field: value}))

        assert response.status_code == 422

    async def test_the_password_is_hashed_not_stored(
        self, staff: AsyncClient, db: AsyncSession
    ) -> None:
        body = _person()
        created = (await staff.post("/api/v1/users", json=body)).json()

        stored = (
            await db.execute(
                text("SELECT password_hash FROM users WHERE id = :id"), {"id": created["id"]}
            )
        ).scalar_one()

        assert stored != body["password"]
        assert stored.startswith("$argon2")
