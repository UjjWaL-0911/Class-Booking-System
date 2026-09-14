"""What a signed-in member can and cannot reach.

Self-service booking's security model is one sentence: **the member being acted
on is derived from the credential, never supplied by the caller.** There is no
member id in any of these routes to tamper with.

So the tests that matter are not the happy path — they are the walls. Two members
must not see each other, and a member must not reach any of the studio endpoints
that were written back when "authenticated" meant "allowed".
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")

WHEN = dt.date(2029, 6, 12)

# Every studio surface as it stood before members existed. A member reaching one
# of these is the failure this feature is most likely to introduce.
STUDIO_READS = [
    "/api/v1/bookings",
    "/api/v1/sessions",
    "/api/v1/members",
    "/api/v1/classes",
    "/api/v1/rooms",
    "/api/v1/users",
    "/api/v1/dashboard",
    "/api/v1/operations",
    "/api/v1/alerts/memberships",
]


async def _a_session(staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]) -> str:
    """A future session with room for everybody. Returns its id."""
    tag = uuid.uuid4().hex[:8]
    room = (await staff.post("/api/v1/rooms", json={"name": f"Studio {tag}"})).json()
    studio_class = (
        await staff.post(
            "/api/v1/classes",
            json={
                "title": f"Class {tag}",
                "description": "",
                "discipline": "yoga",
                "default_duration_min": 60,
                "default_capacity": 20,
            },
        )
    ).json()
    instructor_id = str(
        (
            await db.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": accounts["instructor"]}
            )
        ).scalar_one()
    )
    created = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": studio_class["id"],
            "session_date": WHEN.isoformat(),
            "start_time": "18:00:00",
            "primary_instructor_id": instructor_id,
            "room_id": room["id"],
            "duration_min": 60,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _book(staff: AsyncClient, session_id: str, member_id: str) -> dict[str, Any]:
    response = await staff.post(
        "/api/v1/bookings", json={"session_id": session_id, "member_id": member_id}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _another_member(staff: AsyncClient) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    response = await staff.post(
        "/api/v1/members",
        json={
            "full_name": f"Other {tag}",
            "email": f"other-{tag}@example.com",
            "membership_expiry": "2030-01-01",
            "notes": "",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestMembership:
    async def test_a_member_reads_their_own_membership(
        self, member: AsyncClient, member_account: dict[str, str]
    ) -> None:
        response = await member.get("/api/v1/me/membership")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["email"] == member_account["email"]
        assert body["is_expired"] is False

    async def test_the_shape_is_exactly_what_a_member_is_told(
        self, member: AsyncClient
    ) -> None:
        """The key set, not the absence of one field. Widening this response is
        then a failing test rather than a quiet disclosure."""
        body = (await member.get("/api/v1/me/membership")).json()

        assert set(body) == {"full_name", "email", "membership_expiry", "is_expired"}

    async def test_a_lapsed_member_can_still_read_it(
        self, staff: AsyncClient, api: AsyncClient
    ) -> None:
        """Enabling a login does not grant a membership, so a lapsed member has an
        account that works and bookings that will be refused. This is how they
        learn that before meeting the refusal."""
        tag = uuid.uuid4().hex[:8]
        created = (
            await staff.post(
                "/api/v1/members",
                json={
                    "full_name": f"Lapsed {tag}",
                    "email": f"lapsed-{tag}@example.com",
                    "membership_expiry": "2020-01-01",
                    "notes": "",
                },
            )
        ).json()
        password = "another-long-enough-password"
        enabled = await staff.post(
            f"/api/v1/members/{created['id']}/account", json={"password": password}
        )
        assert enabled.status_code == 201, enabled.text

        signed_in = await api.post(
            "/api/v1/auth/login", json={"email": created["email"], "password": password}
        )
        token = signed_in.json()["access_token"]
        body = (
            await api.get(
                "/api/v1/me/membership", headers={"Authorization": f"Bearer {token}"}
            )
        ).json()

        assert body["is_expired"] is True


class TestMyBookings:
    async def test_an_empty_list_is_not_an_error(self, member: AsyncClient) -> None:
        response = await member.get("/api/v1/me/bookings")

        assert response.status_code == 200
        assert response.json() == []

    async def test_a_member_sees_only_their_own(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
        member_account: dict[str, str],
    ) -> None:
        """The one that would matter most if it broke: two members on one session,
        and each must see exactly one row."""
        session_id = await _a_session(staff, db, accounts)
        mine = await _book(staff, session_id, member_account["id"])
        await _book(staff, session_id, (await _another_member(staff))["id"])

        rows = (await member.get("/api/v1/me/bookings")).json()

        assert len(rows) == 1
        assert rows[0]["id"] == mine["id"]

    async def test_no_row_mentions_anybody_else(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
        member_account: dict[str, str],
    ) -> None:
        """The staff list carries member_id, member_name and member_email on every
        row, because that list is *about* who booked. This shape never had them,
        which is why it is written from scratch rather than filtered."""
        session_id = await _a_session(staff, db, accounts)
        await _book(staff, session_id, member_account["id"])

        row = (await member.get("/api/v1/me/bookings")).json()[0]

        assert set(row) == {
            "id",
            "status",
            "booked_at",
            "session_date",
            "start_time",
            "duration_min",
            "class_title",
            "discipline",
            "instructor_name",
            "room_name",
            "session_has_passed",
            "waitlist_position",
            "can_cancel",
        }

    async def test_a_future_booking_says_it_can_be_cancelled(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
        member_account: dict[str, str],
    ) -> None:
        session_id = await _a_session(staff, db, accounts)
        await _book(staff, session_id, member_account["id"])

        row = (await member.get("/api/v1/me/bookings")).json()[0]

        assert row["status"] == "booked"
        assert row["can_cancel"] is True
        assert row["session_has_passed"] is False
        assert row["waitlist_position"] is None


class TestTheWalls:
    @pytest.mark.parametrize("path", STUDIO_READS)
    async def test_a_member_cannot_reach_a_studio_endpoint(
        self, member: AsyncClient, path: str
    ) -> None:
        """Each of these took any authenticated user before members existed. 403
        rather than an empty 200: the visibility filters would have returned
        nothing, which is safe and still the wrong answer to give a customer."""
        response = await member.get(path)

        assert response.status_code == 403, f"{path} returned {response.status_code}"

    async def test_a_member_cannot_book_through_the_staff_endpoint(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
        member_account: dict[str, str],
    ) -> None:
        """Not even for themselves. That endpoint takes a member_id from the body,
        which is precisely the parameter self-service must never expose."""
        session_id = await _a_session(staff, db, accounts)

        response = await member.post(
            "/api/v1/bookings",
            json={"session_id": session_id, "member_id": member_account["id"]},
        )

        assert response.status_code == 403

    async def test_an_instructor_cannot_read_a_member_surface(
        self, instructor: AsyncClient
    ) -> None:
        """The wall stands in both directions. An instructor has no member record,
        and should be told so rather than handed one."""
        assert (await instructor.get("/api/v1/me/bookings")).status_code == 403
        assert (await instructor.get("/api/v1/me/membership")).status_code == 403

    async def test_anonymous_callers_are_refused(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/me/bookings")).status_code == 401
        assert (await api.get("/api/v1/me/membership")).status_code == 401
