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


async def _a_session(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    *,
    on: dt.date | None = None,
    at: str = "18:00:00",
) -> str:
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
            "session_date": (on or WHEN).isoformat(),
            "start_time": at,
            "primary_instructor_id": instructor_id,
            "room_id": room["id"],
            "duration_min": 60,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _a_session_soon(
    staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
) -> str:
    """A session inside the schedule window, a few days from now.

    The other helper puts sessions in 2029 so they cannot collide with anything
    else the suite has scheduled. `/me/schedule` looks 31 days ahead, so a 2029
    session is correctly absent from it — which is a real answer and a useless
    fixture. The hour is randomised because the instructor is shared across the
    suite and two sessions at one time would trip the exclusion constraint.
    """
    on = dt.date.today() + dt.timedelta(days=3)
    # Derived from a uuid rather than `random`, which the linter flags here for
    # cryptographic unsuitability — true, and irrelevant to picking a lesson slot.
    tag = uuid.uuid4().int
    at = f"{6 + tag % 16:02d}:{(tag // 16) % 60:02d}:00"
    return await _a_session(staff, db, accounts, on=on, at=at)


async def _a_one_seat_session(
    staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
) -> str:
    """A near-future session with exactly one place, so the second booking queues."""
    tag = uuid.uuid4().hex[:8]
    room = (await staff.post("/api/v1/rooms", json={"name": f"One {tag}"})).json()
    studio_class = (
        await staff.post(
            "/api/v1/classes",
            json={
                "title": f"One Seat {tag}",
                "description": "",
                "discipline": "yoga",
                "default_duration_min": 60,
                "default_capacity": 1,
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
    number = uuid.uuid4().int
    created = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": studio_class["id"],
            "session_date": (dt.date.today() + dt.timedelta(days=4)).isoformat(),
            "start_time": f"{6 + number % 16:02d}:{(number // 16) % 60:02d}:00",
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


class TestBookingMyself:
    """A member taking their own place.

    Every rule exercised here belongs to goal 4 and is tested there. What these
    prove is that the member path *reaches* those rules rather than reimplementing
    them — the failure mode being a second booking path that slowly disagrees with
    the first.
    """

    async def test_a_member_books_their_own_place(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        session_id = await _a_session(staff, db, accounts)

        response = await member.post("/api/v1/me/bookings", json={"session_id": session_id})

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "booked"
        assert response.json()["can_cancel"] is True

    async def test_it_appears_on_their_own_list(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        session_id = await _a_session(staff, db, accounts)
        booked = await member.post("/api/v1/me/bookings", json={"session_id": session_id})

        rows = (await member.get("/api/v1/me/bookings")).json()

        assert [row["id"] for row in rows] == [booked.json()["id"]]

    async def test_the_timeline_records_the_member_as_the_actor(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        """Goal 9 gets this for free. Booking yourself and being booked by the desk
        are different facts, and the actor column already distinguished them."""
        session_id = await _a_session(staff, db, accounts)
        booked = (
            await member.post("/api/v1/me/bookings", json={"session_id": session_id})
        ).json()

        actor = (
            await db.execute(
                text(
                    "SELECT u.role FROM booking_events e JOIN users u ON u.id = e.actor_user_id "
                    "WHERE e.booking_id = :b ORDER BY e.id LIMIT 1"
                ),
                {"b": uuid.UUID(booked["id"])},
            )
        ).scalar_one()

        assert actor == "member"

    async def test_booking_twice_is_refused(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        session_id = await _a_session(staff, db, accounts)
        first = await member.post("/api/v1/me/bookings", json={"session_id": session_id})
        assert first.status_code == 201

        again = await member.post("/api/v1/me/bookings", json={"session_id": session_id})

        assert again.status_code == 409

    async def test_a_lapsed_membership_is_refused_at_the_point_of_booking(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], api: AsyncClient
    ) -> None:
        """The rule that lets self-service exist without modelling payment at all.
        The account works; the booking does not."""
        session_id = await _a_session(staff, db, accounts)
        tag = uuid.uuid4().hex[:8]
        lapsed = (
            await staff.post(
                "/api/v1/members",
                json={
                    "full_name": f"Lapsed {tag}",
                    "email": f"lapsed-book-{tag}@example.com",
                    "membership_expiry": "2020-01-01",
                    "notes": "",
                },
            )
        ).json()
        password = "a-perfectly-long-password"
        await staff.post(f"/api/v1/members/{lapsed['id']}/account", json={"password": password})
        token = (
            await api.post(
                "/api/v1/auth/login", json={"email": lapsed["email"], "password": password}
            )
        ).json()["access_token"]

        response = await api.post(
            "/api/v1/me/bookings",
            json={"session_id": session_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422
        assert "expired" in response.json()["message"]


class TestCancellingMyOwn:
    async def test_a_member_cancels_their_own_booking(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        session_id = await _a_session(staff, db, accounts)
        booked = (
            await member.post("/api/v1/me/bookings", json={"session_id": session_id})
        ).json()

        response = await member.post(f"/api/v1/me/bookings/{booked['id']}/cancel", json={})

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cancelled"
        assert response.json()["can_cancel"] is False

    async def test_a_member_cannot_cancel_one_belonging_to_somebody_else(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        """404 rather than 403. Saying "that exists but is not yours" would let
        somebody walk the id space one request at a time."""
        session_id = await _a_session(staff, db, accounts)
        theirs = await _book(staff, session_id, (await _another_member(staff))["id"])

        response = await member.post(f"/api/v1/me/bookings/{theirs['id']}/cancel", json={})

        assert response.status_code == 404

    async def test_cancelling_frees_the_seat_for_the_waitlist(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        member: AsyncClient,
    ) -> None:
        """The promotion is the ordinary one: a member giving up a place runs the
        same code as the desk doing it, so goal 4 keeps working by itself."""
        tag = uuid.uuid4().hex[:8]
        room = (await staff.post("/api/v1/rooms", json={"name": f"Tiny {tag}"})).json()
        one_seat = (
            await staff.post(
                "/api/v1/classes",
                json={
                    "title": f"Tiny {tag}",
                    "description": "",
                    "discipline": "yoga",
                    "default_duration_min": 60,
                    "default_capacity": 1,
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
                "class_id": one_seat["id"],
                "session_date": WHEN.isoformat(),
                "start_time": "07:00:00",
                "primary_instructor_id": instructor_id,
                "room_id": room["id"],
                "duration_min": 60,
            },
        )
        session_id = str(created.json()["id"])
        mine = (
            await member.post("/api/v1/me/bookings", json={"session_id": session_id})
        ).json()
        assert mine["status"] == "booked"
        queued = await _book(staff, session_id, (await _another_member(staff))["id"])
        assert queued["status"] == "waitlisted"

        await member.post(f"/api/v1/me/bookings/{mine['id']}/cancel", json={})

        promoted = (
            await db.execute(
                text("SELECT status FROM bookings WHERE id = :b"),
                {"b": uuid.UUID(queued["id"])},
            )
        ).scalar_one()
        assert promoted == "booked"


class TestMySchedule:
    async def test_it_carries_a_session_id_the_public_one_does_not(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], member: AsyncClient
    ) -> None:
        session_id = await _a_session_soon(staff, db, accounts)

        rows = (await member.get("/api/v1/me/schedule", params={"days": 31})).json()

        assert any(row["id"] == session_id for row in rows)
        assert all("id" in row for row in rows)

    async def test_it_says_which_ones_i_am_already_on(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], member: AsyncClient
    ) -> None:
        """The field that earns this endpoint its existence. Without it the
        interface would decide what each button says by cross-referencing two
        lists in the browser, which is a rule living in the wrong place."""
        session_id = await _a_session_soon(staff, db, accounts)
        booked = await member.post("/api/v1/me/bookings", json={"session_id": session_id})
        assert booked.status_code == 201, booked.text

        rows = (await member.get("/api/v1/me/schedule", params={"days": 31})).json()
        matching = [row for row in rows if row["id"] == session_id]
        others = [row for row in rows if row["id"] != session_id]

        assert matching, "the session just booked is missing from the schedule"
        mine = matching[0]
        assert mine["my_status"] == "booked"
        assert all(row["my_status"] is None for row in others)

    async def test_the_schedule_shows_my_place_in_the_queue(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], member: AsyncClient
    ) -> None:
        """The timetable and the member's own list must answer "where am I?" the
        same way. They did not at first: the schedule said only "on the waiting
        list" while the bookings list said "1st", which is two answers to one
        question — and the timetable is where somebody decides whether to wait."""
        session_id = await _a_one_seat_session(staff, db, accounts)
        await _book(staff, session_id, (await _another_member(staff))["id"])
        queued = await member.post("/api/v1/me/bookings", json={"session_id": session_id})
        assert queued.json()["status"] == "waitlisted"

        row = next(
            r
            for r in (await member.get("/api/v1/me/schedule", params={"days": 31})).json()
            if r["id"] == session_id
        )
        own = next(
            r
            for r in (await member.get("/api/v1/me/bookings")).json()
            if r["id"] == queued.json()["id"]
        )

        assert row["my_waitlist_position"] == 1
        assert row["my_waitlist_position"] == own["waitlist_position"]

    async def test_a_booked_row_has_no_position(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], member: AsyncClient
    ) -> None:
        session_id = await _a_session_soon(staff, db, accounts)
        await member.post("/api/v1/me/bookings", json={"session_id": session_id})

        row = next(
            r
            for r in (await member.get("/api/v1/me/schedule", params={"days": 31})).json()
            if r["id"] == session_id
        )

        assert row["my_status"] == "booked"
        assert row["my_waitlist_position"] is None


class TestOfferedClasses:
    """The catalogue a member browses.

    A different question from the timetable, and the tests reflect that: what
    matters is which classes appear at all, not which sessions.
    """

    async def test_it_lists_what_the_studio_offers(
        self, staff: AsyncClient, member: AsyncClient
    ) -> None:
        tag = uuid.uuid4().hex[:8]
        created = (
            await staff.post(
                "/api/v1/classes",
                json={
                    "title": f"Offered {tag}",
                    "description": "A description a member can read.",
                    "discipline": "pilates",
                    "default_duration_min": 55,
                    "default_capacity": 12,
                },
            )
        ).json()

        rows = (await member.get("/api/v1/me/classes")).json()
        mine = next(r for r in rows if r["id"] == created["id"])

        assert mine["title"] == created["title"]
        assert mine["description"] == "A description a member can read."
        assert mine["default_duration_min"] == 55
        assert mine["upcoming_sessions"] == 0

    async def test_a_class_with_nothing_scheduled_still_appears(
        self, staff: AsyncClient, member: AsyncClient
    ) -> None:
        """It is a real part of what the studio does. Archiving is what "no longer
        offered" means, and an archived class is not on this list at all."""
        tag = uuid.uuid4().hex[:8]
        created = (
            await staff.post(
                "/api/v1/classes",
                json={
                    "title": f"Quiet {tag}",
                    "description": "",
                    "discipline": "yoga",
                    "default_duration_min": 60,
                    "default_capacity": 10,
                },
            )
        ).json()

        rows = (await member.get("/api/v1/me/classes")).json()

        assert any(r["id"] == created["id"] and r["upcoming_sessions"] == 0 for r in rows)

    async def test_an_archived_class_is_gone(
        self, staff: AsyncClient, member: AsyncClient
    ) -> None:
        tag = uuid.uuid4().hex[:8]
        created = (
            await staff.post(
                "/api/v1/classes",
                json={
                    "title": f"Retired {tag}",
                    "description": "",
                    "discipline": "yoga",
                    "default_duration_min": 60,
                    "default_capacity": 10,
                },
            )
        ).json()
        archived = await staff.post(f"/api/v1/classes/{created['id']}/archive")
        assert archived.status_code == 200, archived.text

        rows = (await member.get("/api/v1/me/classes")).json()

        assert all(r["id"] != created["id"] for r in rows)

    async def test_it_counts_the_sessions_coming_up(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], member: AsyncClient
    ) -> None:
        session_id = await _a_session_soon(staff, db, accounts)
        row = next(
            r
            for r in (await member.get("/api/v1/me/schedule", params={"days": 31})).json()
            if r["id"] == session_id
        )

        catalogue = (await member.get("/api/v1/me/classes")).json()
        its_class = next(c for c in catalogue if c["id"] == row["class_id"])

        assert its_class["upcoming_sessions"] >= 1

    async def test_the_shape_carries_no_version_or_timestamps(
        self, member: AsyncClient
    ) -> None:
        """`ClassOut` has `version`, `archived_at`, `created_at` and `updated_at`.
        An optimistic-lock token is meaningless to somebody who cannot edit the
        row, and handing one out invites a client to send it back."""
        rows = (await member.get("/api/v1/me/classes")).json()

        assert rows, "the seeded studio should offer something"
        assert set(rows[0]) == {
            "id",
            "title",
            "discipline",
            "description",
            "default_duration_min",
            "upcoming_sessions",
        }

    async def test_a_studio_user_cannot_read_the_member_catalogue(
        self, instructor: AsyncClient
    ) -> None:
        assert (await instructor.get("/api/v1/me/classes")).status_code == 403
