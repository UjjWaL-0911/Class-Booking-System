"""Recurring generation and attendance export (goal 7).

Goal 7 asks for two separate things and both have a detail that is easy to get
wrong: the generator must report *why* each occurrence was skipped, and the export
must contain every booking rather than only the ones that turned up.

The daylight-saving tests matter more than they look. Adding seven days to a UTC
instant is the obvious implementation and it silently moves an 18:00 class to 17:00
for half the year — correct-looking output, wrong schedule, discovered by a member
standing outside a locked studio.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")


async def _room(staff: AsyncClient) -> str:
    r = await staff.post("/api/v1/rooms", json={"name": f"S {uuid.uuid4().hex[:8]}"})
    return str(r.json()["id"])


async def _class(staff: AsyncClient, **kw: Any) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/classes",
        json={
            "title": f"Class {uuid.uuid4().hex[:6]}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": 20,
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _user_id(db: AsyncSession, email: str) -> str:
    return str(
        (await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})).scalar_one()
    )


async def _pattern(
    staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], **kw: Any
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "class_id": (await _class(staff))["id"],
        "primary_instructor_id": await _user_id(db, accounts["instructor"]),
        "room_id": await _room(staff),
        "start_time": "18:00:00",
        "weekdays": [0],  # Monday
        "date_from": "2027-03-01",
        "date_to": "2027-03-29",
        **kw,
    }
    return base


async def _generate(staff: AsyncClient, pattern: dict[str, Any]) -> dict[str, Any]:
    r = await staff.post("/api/v1/sessions/generate", json=pattern)
    assert r.status_code in (201, 422), r.text
    return dict(r.json())


class TestGeneration:
    async def test_a_weekly_pattern_creates_one_session_per_matching_date(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """1 to 29 March 2027 contains five Mondays."""
        pattern = await _pattern(staff, db, accounts)

        report = await _generate(staff, pattern)

        assert report["requested"] == 5
        assert len(report["created"]) == 5
        assert report["skipped"] == []

    async def test_multiple_weekdays(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        pattern = await _pattern(
            staff,
            db,
            accounts,
            weekdays=[0, 2],
            date_from="2027-03-01",
            date_to="2027-03-14",
        )

        report = await _generate(staff, pattern)

        # Two Mondays and two Wednesdays in that fortnight.
        assert report["requested"] == 4
        assert len(report["created"]) == 4

    async def test_generated_sessions_inherit_the_class_defaults(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff, default_duration_min=45, default_capacity=8)
        pattern = await _pattern(staff, db, accounts, class_id=studio_class["id"])

        report = await _generate(staff, pattern)

        assert {s["duration_min"] for s in report["created"]} == {45}
        assert {s["capacity"] for s in report["created"]} == {8}

    async def test_overrides_apply_to_every_generated_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        pattern = await _pattern(staff, db, accounts, duration_min=90, capacity=6)

        report = await _generate(staff, pattern)

        assert {s["duration_min"] for s in report["created"]} == {90}
        assert {s["capacity"] for s in report["created"]} == {6}

    async def test_an_instructor_cannot_generate(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        pattern = await _pattern(staff, db, accounts)

        response = await instructor.post("/api/v1/sessions/generate", json=pattern)

        assert response.status_code == 403

    async def test_an_archived_class_cannot_be_generated_into(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        await staff.post(f"/api/v1/classes/{studio_class['id']}/archive")
        pattern = await _pattern(staff, db, accounts, class_id=studio_class["id"])

        response = await staff.post("/api/v1/sessions/generate", json=pattern)

        assert response.status_code == 422
        assert "archived" in response.json()["message"]

    async def test_an_oversized_batch_is_refused_with_the_limit(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Each occurrence takes a savepoint, and PostgreSQL caches only 64
        subtransaction ids per backend before every other backend starts paying
        for it. The cap is a real constraint, not an arbitrary number."""
        pattern = await _pattern(
            staff,
            db,
            accounts,
            weekdays=[0, 1, 2, 3, 4, 5, 6],
            date_from="2027-01-01",
            date_to="2028-12-31",
        )

        response = await staff.post("/api/v1/sessions/generate", json=pattern)

        assert response.status_code == 422
        assert "the limit is 200" in response.json()["message"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("weekdays", []),
            ("weekdays", [7]),
            ("weekdays", [0, 0]),
            ("date_to", "2026-01-01"),
        ],
    )
    async def test_invalid_patterns_are_rejected(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        field: str,
        value: Any,
    ) -> None:
        pattern = await _pattern(staff, db, accounts, **{field: value})

        response = await staff.post("/api/v1/sessions/generate", json=pattern)

        assert response.status_code == 422


class TestSkipReporting:
    async def test_a_clash_with_an_existing_session_is_reported_with_the_reason(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 7: the result reports "which were skipped because the chosen
        instructor or room was already booked in an overlapping window"."""
        room = await _room(staff)
        instructor_id = await _user_id(db, accounts["instructor"])
        existing = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": "2027-03-08",
                "start_time": "18:30:00",
                "primary_instructor_id": instructor_id,
                "room_id": room,
            },
        )
        assert existing.status_code == 201

        pattern = await _pattern(
            staff, db, accounts, room_id=room, primary_instructor_id=instructor_id
        )
        report = await _generate(staff, pattern)

        assert len(report["created"]) == 4
        assert len(report["skipped"]) == 1
        skipped = report["skipped"][0]
        assert skipped["session_date"] == "2027-03-08"
        assert skipped["reason"] in ("room_busy", "instructor_busy")
        assert skipped["conflicting_session_id"] == existing.json()["id"]

    async def test_the_reason_distinguishes_room_from_instructor(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """ "Skipped" without saying what it collided with leaves staff to hunt
        through the schedule themselves."""
        busy_room = await _room(staff)
        other_instructor = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :e, 'x', 'Other', 'instructor')"
            ),
            {"id": other_instructor, "e": f"o-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.commit()
        await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": "2027-03-08",
                "start_time": "18:00:00",
                "primary_instructor_id": str(other_instructor),
                "room_id": busy_room,
            },
        )

        pattern = await _pattern(staff, db, accounts, room_id=busy_room)
        report = await _generate(staff, pattern)

        skipped = report["skipped"][0]
        assert skipped["reason"] == "room_busy"
        assert "room is already booked" in skipped["detail"]

    async def test_the_rest_of_the_batch_still_lands(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A savepoint per occurrence. Without it the first conflict aborts the
        transaction and the other four are lost too."""
        room = await _room(staff)
        instructor_id = await _user_id(db, accounts["instructor"])
        for clash_date in ("2027-03-08", "2027-03-22"):
            await staff.post(
                "/api/v1/sessions",
                json={
                    "class_id": (await _class(staff))["id"],
                    "session_date": clash_date,
                    "start_time": "18:00:00",
                    "primary_instructor_id": instructor_id,
                    "room_id": room,
                },
            )

        pattern = await _pattern(
            staff, db, accounts, room_id=room, primary_instructor_id=instructor_id
        )
        report = await _generate(staff, pattern)

        assert len(report["created"]) == 3
        assert len(report["skipped"]) == 2
        assert report["requested"] == 5

    async def test_the_report_matches_what_is_in_the_database(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The batch is one transaction, so "created" is not a hopeful summary."""
        pattern = await _pattern(staff, db, accounts)
        report = await _generate(staff, pattern)

        listed = (await staff.get(f"/api/v1/sessions?class_id={pattern['class_id']}")).json()

        assert listed["total"] == len(report["created"])
        assert {s["id"] for s in listed["items"]} == {s["id"] for s in report["created"]}


class TestDaylightSaving:
    async def test_the_wall_clock_time_survives_a_dst_transition(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An 18:00 class must stay 18:00 either side of the clocks changing.

        Under a UTC-arithmetic implementation the sessions after the transition
        come back an hour out — which is exactly what a member turning up to a
        locked studio would discover.
        """
        from app.core.config import get_settings

        monkeypatch.setenv("STUDIO_TIMEZONE", "Europe/London")
        get_settings.cache_clear()

        # BST begins 28 March 2027; this range spans it.
        pattern = await _pattern(
            staff,
            db,
            accounts,
            weekdays=[6],  # Sunday
            date_from="2027-03-14",
            date_to="2027-04-11",
        )
        report = await _generate(staff, pattern)

        get_settings.cache_clear()

        assert len(report["created"]) == 5
        assert {s["start_time"] for s in report["created"]} == {"18:00:00"}

        # And the underlying instants really do differ by an hour across it.
        instants = sorted(dt.datetime.fromisoformat(s["starts_at"]) for s in report["created"])
        before = instants[0].hour
        after = instants[-1].hour
        assert before != after, "UTC instant should shift when the clocks change"

    async def test_a_nonexistent_local_time_is_skipped_with_that_reason(
        self,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """01:30 does not exist on the spring-forward date. Silently shifting it
        would be worse than saying so."""
        from app.core.config import get_settings

        monkeypatch.setenv("STUDIO_TIMEZONE", "Europe/London")
        get_settings.cache_clear()

        pattern = await _pattern(
            staff,
            db,
            accounts,
            start_time="01:30:00",
            weekdays=[6],
            date_from="2027-03-21",
            date_to="2027-04-04",
        )
        report = await _generate(staff, pattern)

        get_settings.cache_clear()

        skipped = [s for s in report["skipped"] if s["reason"] == "nonexistent_local_time"]
        assert len(skipped) == 1
        assert skipped[0]["session_date"] == "2027-03-28"
        assert "clocks change" in skipped[0]["detail"]


class TestAttendanceExport:
    async def _session_with_bookings(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> tuple[str, list[dict[str, Any]]]:
        r = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": "2027-06-07",
                "start_time": "18:00:00",
                "primary_instructor_id": await _user_id(db, accounts["instructor"]),
                "room_id": await _room(staff),
                "capacity": 2,
            },
        )
        session = r.json()

        members = []
        for name in ("Ada Lovelace", "Grace Hopper", "Katherine Johnson"):
            tag = uuid.uuid4().hex[:8]
            m = await staff.post(
                "/api/v1/members",
                json={
                    "full_name": name,
                    "email": f"{name.split()[0].lower()}-{tag}@example.com",
                    "membership_expiry": "2030-01-01",
                    "notes": "",
                },
            )
            members.append(m.json())
            await staff.post(
                "/api/v1/bookings",
                json={"session_id": session["id"], "member_id": m.json()["id"]},
            )
        return str(session["id"]), members

    async def test_the_export_contains_every_booking_not_only_attendees(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A register that omitted cancellations and absences would be a guest
        list, not an attendance record."""
        session_id, members = await self._session_with_bookings(staff, db, accounts)

        response = await staff.get(f"/api/v1/sessions/{session_id}/attendance.csv")

        assert response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert len(rows) == 3
        assert {r["member_name"] for r in rows} == {m["full_name"] for m in members}
        assert {r["status"] for r in rows} == {"Booked", "Waitlisted"}

    async def test_final_statuses_appear(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session_id, _ = await self._session_with_bookings(staff, db, accounts)
        listed = (await staff.get(f"/api/v1/bookings?session_id={session_id}")).json()
        booked = [b for b in listed["items"] if b["status"] == "booked"]
        await db.execute(
            text("UPDATE sessions SET starts_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": uuid.UUID(session_id)},
        )
        await db.commit()
        await staff.post(f"/api/v1/bookings/{booked[0]['id']}/settle", json={"attended": True})
        await staff.post(f"/api/v1/bookings/{booked[1]['id']}/settle", json={"attended": False})

        response = await staff.get(f"/api/v1/sessions/{session_id}/attendance.csv")

        statuses = {r["status"] for r in csv.DictReader(io.StringIO(response.text))}
        assert "Attended" in statuses
        assert "Absent" in statuses

    async def test_formula_injection_is_neutralised(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The member name is free text typed at a front desk, it reaches this file
        unaltered, and the file is opened in Excel by definition. This is the whole
        distance between a CSV export and a code-execution vector."""
        r = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": "2027-06-14",
                "start_time": "18:00:00",
                "primary_instructor_id": await _user_id(db, accounts["instructor"]),
                "room_id": await _room(staff),
            },
        )
        session_id = r.json()["id"]
        tag = uuid.uuid4().hex[:8]
        member = await staff.post(
            "/api/v1/members",
            json={
                "full_name": '=HYPERLINK("http://evil","click")',
                "email": f"evil-{tag}@example.com",
                "membership_expiry": "2030-01-01",
                "notes": "",
            },
        )
        await staff.post(
            "/api/v1/bookings",
            json={"session_id": session_id, "member_id": member.json()["id"]},
        )

        response = await staff.get(f"/api/v1/sessions/{session_id}/attendance.csv")

        row = next(csv.DictReader(io.StringIO(response.text)))
        assert row["member_name"].startswith("'=")

    async def test_the_response_is_a_downloadable_file(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session_id, _ = await self._session_with_bookings(staff, db, accounts)

        response = await staff.get(f"/api/v1/sessions/{session_id}/attendance.csv")

        assert response.headers["content-type"].startswith("text/csv")
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert "2027-06-07-1800.csv" in disposition

    async def test_an_instructor_can_export_their_own_session(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        session_id, _ = await self._session_with_bookings(staff, db, accounts)

        response = await instructor.get(f"/api/v1/sessions/{session_id}/attendance.csv")

        assert response.status_code == 200

    async def test_an_instructor_cannot_export_someone_elses_session(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        other = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :e, 'x', 'Other', 'instructor')"
            ),
            {"id": other, "e": f"o-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.commit()
        r = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": "2027-07-05",
                "start_time": "18:00:00",
                "primary_instructor_id": str(other),
                "room_id": await _room(staff),
            },
        )

        response = await instructor.get(f"/api/v1/sessions/{r.json()['id']}/attendance.csv")

        assert response.status_code == 404
