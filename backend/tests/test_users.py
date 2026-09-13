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
        """The exact key set, not the absence of `password_hash`.

        Asserting one missing field would pass the day a second one appears.
        Pinning the whole set means widening this response is a failing test
        rather than a leak — which is how `session_rate_minor` arriving showed up
        here, on a list that is staff-only precisely because it now carries one.
        """
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        for row in response.json():
            assert set(row) == {"id", "email", "full_name", "role", "session_rate_minor"}

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


class TestSessionRate:
    """What a colleague is paid to lead one session.

    The arithmetic is the payroll report's problem and is tested there. What
    matters here is who may read a rate, who may set one, and that **null and zero
    stay different** all the way through — "we have not agreed a rate" is a thing
    somebody has to go and fix, and "unpaid" is a decision. A system that quietly
    turns the first into the second underpays somebody without telling anybody.
    """

    async def test_the_rate_is_set_when_the_account_is_created(
        self, staff: AsyncClient
    ) -> None:
        created = await staff.post("/api/v1/users", json=_person(session_rate_minor=250000))
        assert created.status_code == 201, created.text

        listed = {row["id"]: row for row in (await staff.get("/api/v1/users")).json()}

        assert listed[created.json()["id"]]["session_rate_minor"] == 250000

    async def test_a_new_account_may_have_no_rate_yet(self, staff: AsyncClient) -> None:
        """The desk adding an instructor on Monday should not be blocked on a
        number that has to come from whoever agrees rates."""
        created = await staff.post("/api/v1/users", json=_person())
        assert created.status_code == 201

        listed = {row["id"]: row for row in (await staff.get("/api/v1/users")).json()}

        assert listed[created.json()["id"]]["session_rate_minor"] is None

    async def test_staff_can_set_and_change_it(self, staff: AsyncClient) -> None:
        created = (await staff.post("/api/v1/users", json=_person())).json()

        first = await staff.patch(
            f"/api/v1/users/{created['id']}", json={"session_rate_minor": 90000}
        )
        second = await staff.patch(
            f"/api/v1/users/{created['id']}", json={"session_rate_minor": 110000}
        )

        assert first.json()["session_rate_minor"] == 90000
        assert second.status_code == 200
        assert second.json()["session_rate_minor"] == 110000

    async def test_null_clears_it_and_is_not_zero(self, staff: AsyncClient) -> None:
        """Both directions of the distinction, in one test, because it is the one
        thing about this field that is easy to get wrong."""
        created = (await staff.post("/api/v1/users", json=_person(session_rate_minor=5000))).json()

        cleared = await staff.patch(
            f"/api/v1/users/{created['id']}", json={"session_rate_minor": None}
        )
        zeroed = await staff.patch(
            f"/api/v1/users/{created['id']}", json={"session_rate_minor": 0}
        )

        assert cleared.json()["session_rate_minor"] is None
        assert zeroed.json()["session_rate_minor"] == 0

    @pytest.mark.parametrize("rate", [-1, 2_147_483_648])
    async def test_a_rate_outside_the_column_is_refused(
        self, staff: AsyncClient, rate: int
    ) -> None:
        """A negative rate is not a discount, it is a typo — and a slipped decimal
        past the column's ceiling should be a 422 that says so, not an overflow the
        driver reports as a 500."""
        created = (await staff.post("/api/v1/users", json=_person())).json()

        response = await staff.patch(
            f"/api/v1/users/{created['id']}", json={"session_rate_minor": rate}
        )

        assert response.status_code == 422

    async def test_an_instructor_cannot_read_a_rate_here(
        self, instructor: AsyncClient
    ) -> None:
        """They read their own on the reports screen, scoped by the query. This
        list is every colleague's, which is a different thing."""
        assert (await instructor.get("/api/v1/users")).status_code == 403

    async def test_an_instructor_cannot_set_one(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        created = (await staff.post("/api/v1/users", json=_person())).json()

        response = await instructor.patch(
            f"/api/v1/users/{created['id']}", json={"session_rate_minor": 999999}
        )

        assert response.status_code == 403

    async def test_signing_in_does_not_hand_back_a_rate(
        self, staff: AsyncClient, api: AsyncClient
    ) -> None:
        """The reason the field hangs off a subclass rather than `UserOut`: sign-in
        returns `UserOut` to every account on every login, and a model that never
        had the field cannot leak it."""
        body = _person(session_rate_minor=77000)
        assert (await staff.post("/api/v1/users", json=body)).status_code == 201

        signed_in = await api.post(
            "/api/v1/auth/login",
            json={"email": body["email"], "password": body["password"]},
        )

        assert signed_in.status_code == 200, signed_in.text
        assert "session_rate_minor" not in signed_in.json()["user"]

    async def test_an_unknown_person_is_a_404(self, staff: AsyncClient) -> None:
        response = await staff.patch(
            f"/api/v1/users/{uuid.uuid4()}", json={"session_rate_minor": 100}
        )

        assert response.status_code == 404
