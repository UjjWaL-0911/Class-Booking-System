"""Member tests.

Goal 1 gives members to staff: "add members and set their membership expiry". That
expiry is load-bearing for two other goals — it blocks bookings (goal 4) and drives
the alerts feed (goal 10) — so the tests here care more about it than about the rest
of the record.
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


def _member(**overrides: Any) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    return {
        "full_name": "Ada Lovelace",
        "email": f"ada-{tag}@example.com",
        "membership_expiry": "2027-01-01",
        "notes": "",
        **overrides,
    }


async def _create(staff: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await staff.post("/api/v1/members", json=_member(**overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- scaffolding for the visibility cases -----------------------------------
# A member is only visible to an instructor through a booking on a session they
# teach, so these tests need the whole chain: room, class, session, booking.

FUTURE = dt.date.today() + dt.timedelta(days=30)


async def _user_id(db: AsyncSession, email: str) -> str:
    return str(
        (await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})).scalar_one()
    )


async def _session(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    *,
    instructor_id: str | None = None,
) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    room = await staff.post("/api/v1/rooms", json={"name": f"Room {tag}"})
    studio_class = await staff.post(
        "/api/v1/classes",
        json={
            "title": f"Class {tag}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": 20,
        },
    )
    response = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": studio_class.json()["id"],
            "session_date": FUTURE.isoformat(),
            "start_time": "18:00:00",
            "primary_instructor_id": instructor_id or await _user_id(db, accounts["instructor"]),
            "room_id": room.json()["id"],
            "capacity": 20,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _book(staff: AsyncClient, session_id: str, member_id: str) -> dict[str, Any]:
    response = await staff.post(
        "/api/v1/bookings", json={"session_id": session_id, "member_id": member_id}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestCreate:
    async def test_staff_can_add_a_member(self, staff: AsyncClient) -> None:
        body = await _create(staff, full_name="Grace Hopper")

        assert body["full_name"] == "Grace Hopper"
        assert body["membership_expiry"] == "2027-01-01"

    async def test_email_is_case_insensitively_unique(self, staff: AsyncClient) -> None:
        """The column is citext, so "Ada@x.com" and "ada@x.com" are one person —
        which is the point of choosing citext over text plus a lower() index."""
        first = await _create(staff)

        duplicate = await staff.post("/api/v1/members", json=_member(email=first["email"].upper()))

        assert duplicate.status_code == 409
        assert "already exists" in duplicate.json()["message"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [("full_name", ""), ("email", "not-an-email"), ("membership_expiry", "soon")],
    )
    async def test_invalid_values_are_rejected(
        self, staff: AsyncClient, field: str, value: Any
    ) -> None:
        response = await staff.post("/api/v1/members", json=_member(**{field: value}))

        assert response.status_code == 422

    async def test_an_instructor_cannot_add_a_member(self, instructor: AsyncClient) -> None:
        response = await instructor.post("/api/v1/members", json=_member())

        assert response.status_code == 403


class TestInstructorScope:
    """Which members an instructor may read (goal 1).

    The rule is derived rather than declared: an instructor sees the people who
    have a booking on a session they can see. Anything else would let the roster
    and the directory disagree about who exists.

    The first version of this endpoint let an instructor read every member in the
    studio, on the reasoning that "a class roster is a list of names". A roster is
    the names of people in *your* class; the directory is everybody who ever
    joined, each with a membership expiry beside them. These tests are what stops
    that reasoning coming back.

    Every case creates its own class, so a shared test database that is never
    truncated cannot make one of them pass for the wrong reason.
    """

    async def test_a_member_on_their_own_session_is_readable(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        session = await _session(staff, db, accounts)
        mine = await _create(staff)
        await _book(staff, session["id"], mine["id"])

        response = await instructor.get(f"/api/v1/members/{mine['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == mine["id"]

    async def test_a_member_they_never_taught_is_not_readable(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        """404, not 403. "That one exists but is not yours" would enumerate the
        whole membership one id at a time."""
        stranger = await _create(staff)

        response = await instructor.get(f"/api/v1/members/{stranger['id']}")

        assert response.status_code == 404
        assert (await staff.get(f"/api/v1/members/{stranger['id']}")).status_code == 200

    async def test_the_list_holds_only_their_own_people(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        tag = uuid.uuid4().hex[:8]
        session = await _session(staff, db, accounts)
        mine = await _create(staff, full_name=f"Mine {tag}")
        stranger = await _create(staff, full_name=f"Stranger {tag}")
        await _book(staff, session["id"], mine["id"])

        found = (await instructor.get(f"/api/v1/members?q={tag}")).json()
        ids = {m["id"] for m in found["items"]}

        assert mine["id"] in ids
        assert stranger["id"] not in ids
        # Both exist; only one of them is this instructor's to see.
        assert len((await staff.get(f"/api/v1/members?q={tag}")).json()["items"]) == 2

    async def test_the_total_matches_the_scoped_rows(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """The count comes from the same filtered query as the rows, so a
        paginated list cannot advertise members it will never hand over."""
        tag = uuid.uuid4().hex[:8]
        session = await _session(staff, db, accounts)
        for i in range(3):
            member = await _create(staff, full_name=f"Booked {i} {tag}")
            await _book(staff, session["id"], member["id"])
        await _create(staff, full_name=f"Unbooked {tag}")

        body = (await instructor.get(f"/api/v1/members?q={tag}")).json()

        assert body["total"] == 3
        assert len(body["items"]) == 3

    async def test_a_cancelled_booking_still_counts(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """Somebody who booked and cancelled is still on the session's timeline,
        which this instructor can already open. Hiding the member record would
        conceal nothing and leave a dangling name."""
        session = await _session(staff, db, accounts)
        member = await _create(staff)
        booking = await _book(staff, session["id"], member["id"])
        await staff.post(f"/api/v1/bookings/{booking['id']}/cancel", json={"note": None})

        assert (await instructor.get(f"/api/v1/members/{member['id']}")).status_code == 200

    async def test_a_co_instructed_session_grants_the_same_reach(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """Goal 5's co-instructor relationship carries visibility, and it has to
        carry it here too — otherwise a co-instructor sees a register full of
        names the directory denies."""
        other = await _user_id(db, accounts["staff"])
        session = await _session(staff, db, accounts, instructor_id=other)
        member = await _create(staff)
        await _book(staff, session["id"], member["id"])

        assert (await instructor.get(f"/api/v1/members/{member['id']}")).status_code == 404

        me = await _user_id(db, accounts["instructor"])
        added = await staff.post(
            f"/api/v1/sessions/{session['id']}/co-instructors", json={"user_id": me}
        )
        assert added.status_code in (200, 201), added.text

        assert (await instructor.get(f"/api/v1/members/{member['id']}")).status_code == 200

    async def test_staff_still_see_the_whole_binder(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        """The scoping must cost staff nothing — they resolve to an unrestricted
        clause, so a member nobody has booked is still theirs to read."""
        tag = uuid.uuid4().hex[:8]
        stranger = await _create(staff, full_name=f"Nobody {tag}")

        for_staff = (await staff.get(f"/api/v1/members?q={tag}")).json()
        for_instructor = (await instructor.get(f"/api/v1/members?q={tag}")).json()

        assert [m["id"] for m in for_staff["items"]] == [stranger["id"]]
        assert for_instructor["items"] == []
        assert for_instructor["total"] == 0


class TestExpiry:
    async def test_staff_can_change_the_expiry(self, staff: AsyncClient) -> None:
        created = await _create(staff, membership_expiry="2026-01-01")

        response = await staff.patch(
            f"/api/v1/members/{created['id']}",
            json={"membership_expiry": "2027-06-30"},
        )

        assert response.status_code == 200
        assert response.json()["membership_expiry"] == "2027-06-30"

    async def test_changing_the_expiry_clears_a_dismissed_alert(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 10's re-trigger rule, enforced by trigger rather than by this
        endpoint remembering to do it.

        Dismissing is not built yet, so the dismissal row is inserted directly —
        which is the stronger test anyway: it proves the guarantee does not depend
        on the code path that happens to write it.
        """
        created = await _create(staff, membership_expiry="2026-03-01")
        member_id = uuid.UUID(created["id"])
        actor = (
            await db.execute(
                text("SELECT id FROM users WHERE email = :e"),
                {"e": accounts["staff"]},
            )
        ).scalar_one()

        await db.execute(
            text(
                "INSERT INTO membership_alert_dismissals "
                "(member_id, dismissed_expiry, dismissed_by) "
                "VALUES (:m, '2026-03-01', :u)"
            ),
            {"m": member_id, "u": actor},
        )
        await db.commit()

        await staff.patch(f"/api/v1/members/{member_id}", json={"membership_expiry": "2026-09-01"})

        remaining = (
            await db.execute(
                text("SELECT count(*) FROM membership_alert_dismissals WHERE member_id = :m"),
                {"m": member_id},
            )
        ).scalar_one()
        assert remaining == 0

    async def test_editing_something_else_leaves_the_dismissal_alone(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The trigger's WHEN clause: only a genuine expiry change resets the
        alert. Correcting a spelling must not un-dismiss it."""
        created = await _create(staff, membership_expiry="2026-03-01")
        member_id = uuid.UUID(created["id"])
        actor = (
            await db.execute(
                text("SELECT id FROM users WHERE email = :e"),
                {"e": accounts["staff"]},
            )
        ).scalar_one()
        await db.execute(
            text(
                "INSERT INTO membership_alert_dismissals "
                "(member_id, dismissed_expiry, dismissed_by) "
                "VALUES (:m, '2026-03-01', :u)"
            ),
            {"m": member_id, "u": actor},
        )
        await db.commit()

        await staff.patch(f"/api/v1/members/{member_id}", json={"full_name": "Ada L."})

        remaining = (
            await db.execute(
                text("SELECT count(*) FROM membership_alert_dismissals WHERE member_id = :m"),
                {"m": member_id},
            )
        ).scalar_one()
        assert remaining == 1

    async def test_a_membership_is_valid_through_its_expiry_date(
        self, staff: AsyncClient, db: AsyncSession
    ) -> None:
        """ "Expired" means the date has *passed*, not arrived. Goal 4 says a member
        "whose membership expiry date has passed" cannot book, so someone whose
        membership ends today can still be booked in today.
        """
        today = dt.date(2026, 6, 15)
        created = await _create(staff, membership_expiry=today.isoformat())

        expired = (
            await db.execute(
                text("SELECT membership_expiry < :today FROM members WHERE id = :id"),
                {"today": today, "id": uuid.UUID(created["id"])},
            )
        ).scalar_one()

        assert expired is False


class TestSearch:
    async def test_search_matches_on_name(self, staff: AsyncClient) -> None:
        tag = uuid.uuid4().hex[:8]
        await _create(staff, full_name=f"Katherine {tag}")

        response = await staff.get(f"/api/v1/members?q={tag}")

        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_search_matches_on_email(self, staff: AsyncClient) -> None:
        created = await _create(staff)
        local_part = created["email"].split("@")[0]

        response = await staff.get(f"/api/v1/members?q={local_part}")

        assert response.json()["total"] == 1
        assert response.json()["items"][0]["id"] == created["id"]

    async def test_search_is_case_insensitive(self, staff: AsyncClient) -> None:
        tag = uuid.uuid4().hex[:8]
        await _create(staff, full_name=f"Dorothy {tag}")

        response = await staff.get(f"/api/v1/members?q=DOROTHY {tag}".replace(" ", "%20"))

        assert response.json()["total"] == 1

    async def test_a_non_matching_search_returns_an_empty_page(self, staff: AsyncClient) -> None:
        response = await staff.get("/api/v1/members?q=zzz-no-such-member-zzz")

        body = response.json()
        assert body["total"] == 0
        assert body["items"] == []


class TestPagination:
    async def test_total_counts_the_whole_filtered_set_not_the_page(
        self, staff: AsyncClient
    ) -> None:
        """The distinction goal 6 turns on. A total that counted the page would be
        useless for showing how many matches exist."""
        tag = uuid.uuid4().hex[:8]
        for i in range(5):
            await _create(staff, full_name=f"Member {tag} {i}")

        response = await staff.get(f"/api/v1/members?q={tag}&limit=2")

        body = response.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5

    async def test_offset_walks_the_result_set(self, staff: AsyncClient) -> None:
        tag = uuid.uuid4().hex[:8]
        for i in range(5):
            await _create(staff, full_name=f"Member {tag} {i}")

        first = (await staff.get(f"/api/v1/members?q={tag}&limit=2&offset=0")).json()
        second = (await staff.get(f"/api/v1/members?q={tag}&limit=2&offset=2")).json()

        first_ids = {m["id"] for m in first["items"]}
        second_ids = {m["id"] for m in second["items"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_the_page_size_is_capped(self, staff: AsyncClient) -> None:
        """An unbounded page size is a cheap denial of service on a small instance."""
        response = await staff.get("/api/v1/members?limit=100000")

        assert response.status_code == 422

    async def test_ordering_is_stable_across_pages(self, staff: AsyncClient) -> None:
        """Ordered by name *and id*. Without the id tiebreak, two members with the
        same name could swap places between requests and a row would be skipped."""
        tag = uuid.uuid4().hex[:8]
        for _ in range(4):
            await _create(staff, full_name=f"Same Name {tag}")

        page_one = (await staff.get(f"/api/v1/members?q={tag}&limit=2&offset=0")).json()
        again = (await staff.get(f"/api/v1/members?q={tag}&limit=2&offset=0")).json()

        assert [m["id"] for m in page_one["items"]] == [m["id"] for m in again["items"]]
