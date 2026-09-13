"""Room utilisation and instructor payroll (two stretch ideas).

Neither is a goal. The tests that matter are the ones about *definitions* rather
than arithmetic: which sessions count, who gets paid for a class with two
instructors on it, and what happens to a total when somebody has no rate. Getting
the sum wrong would be caught by anybody reading the screen; getting the definition
wrong would not.
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

PATH = "/api/v1/operations"
WHEN = dt.date(2027, 5, 10)


async def _user_id(db: AsyncSession, email: str) -> str:
    row = await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    return str(row.scalar_one())


async def _rate(db: AsyncSession, user_id: str, minor: int | None) -> None:
    await db.execute(
        text("UPDATE users SET session_rate_minor = :r WHERE id = :id"),
        {"r": minor, "id": uuid.UUID(user_id)},
    )
    await db.commit()


async def _room(staff: AsyncClient, name: str | None = None) -> dict[str, Any]:
    response = await staff.post(
        "/api/v1/rooms", json={"name": name or f"Room {uuid.uuid4().hex[:8]}"}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _class(staff: AsyncClient) -> dict[str, Any]:
    response = await staff.post(
        "/api/v1/classes",
        json={
            "title": f"Ops {uuid.uuid4().hex[:8]}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": 10,
        },
    )
    return dict(response.json())


async def _session(
    staff: AsyncClient,
    *,
    class_id: str,
    room_id: str,
    instructor_id: str,
    on: dt.date = WHEN,
    at: str = "18:00:00",
    duration: int = 60,
) -> dict[str, Any]:
    response = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": class_id,
            "session_date": on.isoformat(),
            "start_time": at,
            "primary_instructor_id": instructor_id,
            "room_id": room_id,
            "duration_min": duration,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _report(staff: AsyncClient, *, days: int = 2) -> dict[str, Any]:
    response = await staff.get(
        PATH,
        params={
            "date_from": (WHEN - dt.timedelta(days=days)).isoformat(),
            "date_to": (WHEN + dt.timedelta(days=days)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestRoomUtilisation:
    async def test_minutes_add_up_across_sessions(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        room = await _room(staff)
        studio_class = await _class(staff)
        instructor = await _user_id(db, accounts["instructor"])
        await _session(
            staff, class_id=studio_class["id"], room_id=room["id"],
            instructor_id=instructor, at="09:00:00", duration=45,
        )
        await _session(
            staff, class_id=studio_class["id"], room_id=room["id"],
            instructor_id=instructor, at="11:00:00", duration=90,
        )

        rooms = (await _report(staff))["rooms"]
        mine = next(r for r in rooms if r["room_id"] == room["id"])

        assert mine["sessions"] == 2
        assert mine["minutes_booked"] == 135

    async def test_an_unused_room_still_appears(
        self, staff: AsyncClient
    ) -> None:
        """The most interesting row in a utilisation report is the room nothing
        happened in, and an inner join would drop it."""
        idle = await _room(staff)

        rooms = (await _report(staff))["rooms"]
        mine = next((r for r in rooms if r["room_id"] == idle["id"]), None)

        assert mine is not None
        assert mine["sessions"] == 0
        assert mine["minutes_booked"] == 0

    async def test_a_deleted_session_stops_counting(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        room = await _room(staff)
        studio_class = await _class(staff)
        session = await _session(
            staff,
            class_id=studio_class["id"],
            room_id=room["id"],
            instructor_id=await _user_id(db, accounts["instructor"]),
        )
        before = next(r for r in (await _report(staff))["rooms"] if r["room_id"] == room["id"])
        assert before["sessions"] == 1

        await staff.delete(f"/api/v1/sessions/{session['id']}")

        after = next(r for r in (await _report(staff))["rooms"] if r["room_id"] == room["id"])
        assert after["sessions"] == 0

    async def test_sessions_outside_the_window_do_not_count(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        room = await _room(staff)
        studio_class = await _class(staff)
        await _session(
            staff,
            class_id=studio_class["id"],
            room_id=room["id"],
            instructor_id=await _user_id(db, accounts["instructor"]),
            on=WHEN + dt.timedelta(days=40),
        )

        mine = next(r for r in (await _report(staff))["rooms"] if r["room_id"] == room["id"])

        assert mine["sessions"] == 0


class TestInstructorPay:
    async def test_pay_is_sessions_times_rate(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        instructor = await _user_id(db, accounts["instructor"])
        await _rate(db, instructor, 250000)  # 2,500.00 in minor units
        studio_class = await _class(staff)
        for at in ("09:00:00", "11:00:00", "13:00:00"):
            await _session(
                staff,
                class_id=studio_class["id"],
                room_id=(await _room(staff))["id"],
                instructor_id=instructor,
                at=at,
            )

        rows = (await _report(staff))["instructors"]
        mine = next(r for r in rows if r["instructor_id"] == instructor)

        assert mine["sessions_taught"] == 3
        assert mine["minutes_taught"] == 180
        assert mine["session_rate_minor"] == 250000
        assert mine["total_minor"] == 750000

    async def test_no_rate_means_null_not_zero(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """"We have not decided what to pay them" and "they are owed nothing" are
        different facts, and only one is safe to act on."""
        instructor = await _user_id(db, accounts["instructor"])
        await _rate(db, instructor, None)
        studio_class = await _class(staff)
        await _session(
            staff,
            class_id=studio_class["id"],
            room_id=(await _room(staff))["id"],
            instructor_id=instructor,
        )

        rows = (await _report(staff))["instructors"]
        mine = next(r for r in rows if r["instructor_id"] == instructor)

        assert mine["sessions_taught"] >= 1
        assert mine["session_rate_minor"] is None
        assert mine["total_minor"] is None

    async def test_the_grand_total_is_withheld_when_a_rate_is_missing(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A total that quietly omits somebody is worse than no total, because it
        looks like an answer."""
        instructor = await _user_id(db, accounts["instructor"])
        await _rate(db, instructor, None)
        studio_class = await _class(staff)
        await _session(
            staff,
            class_id=studio_class["id"],
            room_id=(await _room(staff))["id"],
            instructor_id=instructor,
        )

        assert (await _report(staff))["payroll_total_minor"] is None

    async def test_only_the_primary_instructor_is_paid(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Co-instructing is help rather than delivery. Paying two people a full
        session rate for one class is a policy decision this report should not make
        on the studio's behalf."""
        lead = await _user_id(db, accounts["instructor"])
        helper = await _user_id(db, accounts["staff"])
        await _rate(db, lead, 100)
        await _rate(db, helper, 100)
        studio_class = await _class(staff)
        session = await _session(
            staff,
            class_id=studio_class["id"],
            room_id=(await _room(staff))["id"],
            instructor_id=lead,
        )
        added = await staff.post(
            f"/api/v1/sessions/{session['id']}/co-instructors", json={"user_id": helper}
        )
        assert added.status_code in (200, 201), added.text

        rows = (await _report(staff))["instructors"]
        by_id = {r["instructor_id"]: r for r in rows}

        assert by_id[lead]["sessions_taught"] == 1
        assert helper not in by_id or by_id[helper]["sessions_taught"] == 0

    async def test_somebody_who_taught_nothing_is_left_out(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A payroll report listing everybody at zero is a list of everybody."""
        idle = await _user_id(db, accounts["staff"])
        await _rate(db, idle, 500)

        rows = (await _report(staff))["instructors"]

        assert all(r["sessions_taught"] > 0 for r in rows)


class TestAccess:
    async def test_an_instructor_cannot_read_it(self, instructor: AsyncClient) -> None:
        """Utilisation is commercially sensitive and payroll more so — an instructor
        must not be able to read what a colleague is paid."""
        assert (await instructor.get(PATH)).status_code == 403

    async def test_anonymous_callers_are_refused(self, api: AsyncClient) -> None:
        assert (await api.get(PATH)).status_code == 401

    async def test_the_window_defaults_to_the_last_thirty_days(
        self, staff: AsyncClient
    ) -> None:
        """Both questions are about what already happened, so the default window
        looks backwards — unlike every other date range in this API."""
        body = (await staff.get(PATH)).json()

        starts = dt.date.fromisoformat(body["starts"])
        ends = dt.date.fromisoformat(body["ends"])
        assert (ends - starts) == dt.timedelta(days=30)
        assert ends <= dt.date.today() + dt.timedelta(days=1)
