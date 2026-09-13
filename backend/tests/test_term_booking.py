"""Booking a member into a whole term (the "recurring bookings" stretch idea).

Not one of the ten goals. The property worth testing is not that it books things —
it is that **it books them through the same rules a single booking obeys**, and
reports honestly when one of those rules refuses. A bulk path with its own copy of
the booking rules would pass a naive test and disagree with the single path the
first time a membership lapsed mid-term.
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

PATH = "/api/v1/bookings/term"
# Far enough out that "already started" never fires by accident, and fixed so the
# weekday arithmetic in these tests is stable.
TERM_START = dt.date(2027, 3, 1)  # a Monday


async def _user_id(db: AsyncSession, email: str) -> str:
    row = await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    return str(row.scalar_one())


async def _class(staff: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await staff.post(
        "/api/v1/classes",
        json={
            "title": f"Term {uuid.uuid4().hex[:8]}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": 20,
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _member(staff: AsyncClient, **overrides: Any) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    response = await staff.post(
        "/api/v1/members",
        json={
            "full_name": f"Termly {tag}",
            "email": f"t-{tag}@example.com",
            "membership_expiry": "2030-01-01",
            "notes": "",
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _session(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    class_id: str,
    on: dt.date,
    *,
    capacity: int = 20,
    at: str = "18:00:00",
) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    room = await staff.post("/api/v1/rooms", json={"name": f"R {tag}"})
    response = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": class_id,
            "session_date": on.isoformat(),
            "start_time": at,
            "primary_instructor_id": await _user_id(db, accounts["instructor"]),
            "room_id": room.json()["id"],
            "capacity": capacity,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _weekly(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    class_id: str,
    weeks: int = 4,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """`weeks` Mondays in a row, built one at a time so each gets its own room."""
    return [
        await _session(
            staff, db, accounts, class_id, TERM_START + dt.timedelta(weeks=w), **kwargs
        )
        for w in range(weeks)
    ]


def _body(member: str, studio_class: str, **overrides: Any) -> dict[str, Any]:
    return {
        "member_id": member,
        "class_id": studio_class,
        "date_from": TERM_START.isoformat(),
        "date_to": (TERM_START + dt.timedelta(weeks=8)).isoformat(),
        **overrides,
    }


class TestTheHappyTerm:
    async def test_every_session_in_the_range_is_booked(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        sessions = await _weekly(staff, db, accounts, studio_class["id"], weeks=4)
        member = await _member(staff)

        response = await staff.post(PATH, json=_body(member["id"], studio_class["id"]))

        assert response.status_code == 201, response.text
        report = response.json()
        assert report["requested"] == 4
        assert len(report["booked"]) == 4
        assert report["waitlisted"] == []
        assert report["skipped"] == []
        assert {o["session_id"] for o in report["booked"]} == {s["id"] for s in sessions}

    async def test_the_bookings_actually_exist_afterwards(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The report and the database have to agree — the whole thing runs in one
        transaction so that they cannot come apart."""
        studio_class = await _class(staff)
        await _weekly(staff, db, accounts, studio_class["id"], weeks=3)
        member = await _member(staff)

        await staff.post(PATH, json=_body(member["id"], studio_class["id"]))

        rows = (
            await staff.get(f"/api/v1/bookings?class_id={studio_class['id']}&limit=50")
        ).json()
        assert rows["total"] == 3

    async def test_sessions_outside_the_range_are_untouched(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        await _weekly(staff, db, accounts, studio_class["id"], weeks=2)
        far = await _session(
            staff, db, accounts, studio_class["id"], TERM_START + dt.timedelta(weeks=20)
        )
        member = await _member(staff)

        report = (
            await staff.post(PATH, json=_body(member["id"], studio_class["id"]))
        ).json()

        assert report["requested"] == 2
        assert far["id"] not in {o["session_id"] for o in report["booked"]}


class TestWeekdayFilter:
    async def test_only_the_chosen_weekdays_are_booked(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A member joining a Monday/Wednesday class mid-term wants the Mondays and
        Wednesdays that already exist — not every session of the class."""
        studio_class = await _class(staff)
        monday = await _session(staff, db, accounts, studio_class["id"], TERM_START)
        wednesday = await _session(
            staff, db, accounts, studio_class["id"], TERM_START + dt.timedelta(days=2)
        )
        friday = await _session(
            staff, db, accounts, studio_class["id"], TERM_START + dt.timedelta(days=4)
        )
        member = await _member(staff)

        report = (
            await staff.post(
                PATH, json=_body(member["id"], studio_class["id"], weekdays=[0, 2])
            )
        ).json()

        booked = {o["session_id"] for o in report["booked"]}
        assert booked == {monday["id"], wednesday["id"]}
        assert friday["id"] not in booked

    async def test_a_repeated_or_invalid_weekday_is_refused(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        member = await _member(staff)

        for weekdays in ([0, 0], [7], [-1]):
            response = await staff.post(
                PATH, json=_body(member["id"], studio_class["id"], weekdays=weekdays)
            )
            assert response.status_code == 422, weekdays


class TestTheRulesStillApply:
    """Each of these is a rule the single-booking endpoint enforces. The point is
    that the bulk path gets them from the same place rather than reimplementing
    them — so these assert the *report*, which is the only visible difference."""

    async def test_a_full_session_waitlists_rather_than_failing(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        sessions = await _weekly(staff, db, accounts, studio_class["id"], weeks=2, capacity=1)
        # Fill the first week with somebody else.
        other = await _member(staff)
        await staff.post(
            "/api/v1/bookings",
            json={"session_id": sessions[0]["id"], "member_id": other["id"]},
        )
        member = await _member(staff)

        report = (
            await staff.post(PATH, json=_body(member["id"], studio_class["id"]))
        ).json()

        assert len(report["booked"]) == 1
        assert len(report["waitlisted"]) == 1
        assert report["waitlisted"][0]["session_id"] == sessions[0]["id"]
        assert report["skipped"] == []

    async def test_an_expired_membership_skips_every_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        await _weekly(staff, db, accounts, studio_class["id"], weeks=3)
        member = await _member(staff, membership_expiry="2020-01-01")

        report = (
            await staff.post(PATH, json=_body(member["id"], studio_class["id"]))
        ).json()

        assert report["booked"] == []
        assert len(report["skipped"]) == 3
        assert {o["reason"] for o in report["skipped"]} == {"membership_expired"}
        assert "expired" in report["skipped"][0]["detail"]

    async def test_a_session_already_booked_is_skipped_not_duplicated(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The partial unique index would refuse the second booking anyway. What
        matters is that the refusal rolls back one candidate rather than the term."""
        studio_class = await _class(staff)
        sessions = await _weekly(staff, db, accounts, studio_class["id"], weeks=3)
        member = await _member(staff)
        await staff.post(
            "/api/v1/bookings",
            json={"session_id": sessions[1]["id"], "member_id": member["id"]},
        )

        report = (
            await staff.post(PATH, json=_body(member["id"], studio_class["id"]))
        ).json()

        assert len(report["booked"]) == 2
        assert len(report["skipped"]) == 1
        assert report["skipped"][0]["session_id"] == sessions[1]["id"]
        assert report["skipped"][0]["reason"] == "already_booked"

    async def test_an_archived_class_books_nothing(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        await _weekly(staff, db, accounts, studio_class["id"], weeks=2)
        await staff.post(f"/api/v1/classes/{studio_class['id']}/archive")
        member = await _member(staff)

        report = (
            await staff.post(PATH, json=_body(member["id"], studio_class["id"]))
        ).json()

        assert report["booked"] == []
        assert {o["reason"] for o in report["skipped"]} == {"class_archived"}


class TestAudit:
    async def test_each_booking_gets_its_own_timeline(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 9 does not get a discount for bulk. Fourteen bookings made at once
        are still fourteen bookings, each with its own created event."""
        studio_class = await _class(staff)
        await _weekly(staff, db, accounts, studio_class["id"], weeks=2)
        member = await _member(staff)

        report = (
            await staff.post(
                PATH, json=_body(member["id"], studio_class["id"], note="Spring term")
            )
        ).json()

        for outcome in report["booked"]:
            timeline = (
                await staff.get(f"/api/v1/bookings/{outcome['booking_id']}/timeline")
            ).json()
            created = [e for e in timeline["events"] if e["event_type"] == "created"]
            assert len(created) == 1
            assert created[0]["note"] == "Spring term"
            assert created[0]["is_system"] is False


class TestAccess:
    async def test_an_instructor_cannot_bulk_book(
        self, instructor: AsyncClient, staff: AsyncClient
    ) -> None:
        """Goal 1 bars instructors from creating bookings, and doing fourteen at
        once is not an exception to that."""
        studio_class = await _class(staff)
        member = await _member(staff)

        response = await instructor.post(PATH, json=_body(member["id"], studio_class["id"]))

        assert response.status_code == 403

    async def test_an_unknown_class_is_a_404_not_an_empty_report(
        self, staff: AsyncClient
    ) -> None:
        """"Nothing matched" and "that class does not exist" look identical in a
        report of length zero, and only one of them deserves attention."""
        member = await _member(staff)

        response = await staff.post(PATH, json=_body(member["id"], str(uuid.uuid4())))

        assert response.status_code == 404

    async def test_a_backwards_range_is_refused(self, staff: AsyncClient) -> None:
        studio_class = await _class(staff)
        member = await _member(staff)

        response = await staff.post(
            PATH,
            json=_body(
                member["id"],
                studio_class["id"],
                date_from=TERM_START.isoformat(),
                date_to=(TERM_START - dt.timedelta(days=1)).isoformat(),
            ),
        )

        assert response.status_code == 422
