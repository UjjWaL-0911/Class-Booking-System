"""Booking lifecycle tests (goal 4) and the immutable timeline (goal 9).

Goal 4 spells out exact rules, and the brief says those specifics "are the actual
ask, not just the bold headline". So the tests are organised around them: what makes
a booking Booked rather than Waitlisted, which moves are illegal and what the server
says when one is attempted, and what happens to the waitlist when a seat frees.
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

FUTURE = dt.date(2027, 5, 4)
PAST = dt.date(2020, 1, 6)


# --------------------------------------------------------------------- fixtures


async def _room(staff: AsyncClient) -> str:
    r = await staff.post("/api/v1/rooms", json={"name": f"Studio {uuid.uuid4().hex[:8]}"})
    return str(r.json()["id"])


async def _class(staff: AsyncClient, capacity: int = 20) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/classes",
        json={
            "title": f"Class {uuid.uuid4().hex[:6]}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _user_id(db: AsyncSession, email: str) -> str:
    return str(
        (await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})).scalar_one()
    )


async def _session(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    *,
    capacity: int = 2,
    when: dt.date = FUTURE,
    instructor_id: str | None = None,
) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": (await _class(staff))["id"],
            "session_date": when.isoformat(),
            "start_time": "18:00:00",
            "primary_instructor_id": instructor_id or await _user_id(db, accounts["instructor"]),
            "room_id": await _room(staff),
            "capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _member(
    staff: AsyncClient, *, expiry: str = "2028-01-01", name: str = "Member"
) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/members",
        json={
            "full_name": f"{name} {uuid.uuid4().hex[:4]}",
            "email": f"m-{uuid.uuid4().hex[:10]}@example.com",
            "membership_expiry": expiry,
            "notes": "",
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _book(staff: AsyncClient, session_id: str, member_id: str) -> tuple[int, dict[str, Any]]:
    r = await staff.post(
        "/api/v1/bookings",
        json={"session_id": session_id, "member_id": member_id},
    )
    return r.status_code, dict(r.json()) if r.content else {}


# ------------------------------------------------------------------- placement


class TestPlacement:
    async def test_a_booking_with_capacity_is_booked_directly(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 4: "succeeds *directly* to Booked". No confirmation step, which is
        why this system needs no seat-hold mechanism."""
        session = await _session(staff, db, accounts, capacity=2)
        member = await _member(staff)

        code, body = await _book(staff, session["id"], member["id"])

        assert code == 201
        assert body["status"] == "booked"

    async def test_a_booking_on_a_full_session_is_waitlisted(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=1)
        await _book(staff, session["id"], (await _member(staff))["id"])

        code, body = await _book(staff, session["id"], (await _member(staff))["id"])

        assert code == 201
        assert body["status"] == "waitlisted"

    async def test_the_seat_count_reflects_bookings(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=3)
        for _ in range(2):
            await _book(staff, session["id"], (await _member(staff))["id"])

        after = (await staff.get(f"/api/v1/sessions/{session['id']}")).json()

        assert after["booked_count"] == 2
        assert after["seats_remaining"] == 1

    async def test_capacity_is_never_exceeded(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=2)
        statuses = []
        for _ in range(5):
            _, body = await _book(staff, session["id"], (await _member(staff))["id"])
            statuses.append(body["status"])

        assert statuses == ["booked", "booked", "waitlisted", "waitlisted", "waitlisted"]


# -------------------------------------------------------- rejected creations


class TestRejectedCreations:
    """Goal 4: "Any other move must be rejected by the server with a message
    explaining why." Each of these asserts on the message, not just the code."""

    async def test_an_expired_member_cannot_book(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        member = await _member(staff, expiry="2020-08-12")

        code, body = await _book(staff, session["id"], member["id"])

        assert code == 422
        assert "membership expired on 12 Aug 2020" in body["message"]

    async def test_a_membership_expiring_today_can_still_book(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 4 says "has passed", not "has arrived"."""
        from app.core.config import get_settings

        studio_today = dt.datetime.now(dt.UTC).astimezone(get_settings().tz).date()
        session = await _session(staff, db, accounts)
        member = await _member(staff, expiry=studio_today.isoformat())

        code, _ = await _book(staff, session["id"], member["id"])

        assert code == 201

    async def test_a_member_cannot_be_booked_twice_on_one_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        member = await _member(staff)
        await _book(staff, session["id"], member["id"])

        code, body = await _book(staff, session["id"], member["id"])

        assert code == 409
        assert "already has a booking" in body["message"]

    async def test_a_cancelled_member_can_be_booked_again(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The uniqueness rule covers only the two *active* statuses."""
        session = await _session(staff, db, accounts)
        member = await _member(staff)
        _, booking = await _book(staff, session["id"], member["id"])
        await staff.post(f"/api/v1/bookings/{booking['id']}/cancel", json={})

        code, _ = await _book(staff, session["id"], member["id"])

        assert code == 201

    async def test_an_archived_class_takes_no_bookings(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        await staff.post(f"/api/v1/classes/{session['class_id']}/archive")

        code, body = await _book(staff, session["id"], (await _member(staff))["id"])

        assert code == 422
        assert "archived" in body["message"]

    async def test_a_started_session_takes_no_bookings(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """An interpretation rather than a stated rule: a booking created after the
        session began could never be legally settled, since settlement requires the
        session to have started *and* the booking to be Booked."""
        session = await _session(staff, db, accounts, when=PAST)

        code, body = await _book(staff, session["id"], (await _member(staff))["id"])

        assert code == 422
        assert "already started" in body["message"]

    async def test_an_instructor_cannot_create_a_booking(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        session = await _session(staff, db, accounts)
        member = await _member(staff)

        response = await instructor.post(
            "/api/v1/bookings",
            json={"session_id": session["id"], "member_id": member["id"]},
        )

        assert response.status_code == 403


# ------------------------------------------------------ cancel and promotion


class TestCancellationAndPromotion:
    async def test_cancelling_a_booked_booking_promotes_the_earliest_waitlisted(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The heart of goal 4."""
        session = await _session(staff, db, accounts, capacity=1)
        _, first = await _book(staff, session["id"], (await _member(staff))["id"])
        _, second = await _book(staff, session["id"], (await _member(staff))["id"])
        _, third = await _book(staff, session["id"], (await _member(staff))["id"])
        assert (second["status"], third["status"]) == ("waitlisted", "waitlisted")

        result = await staff.post(f"/api/v1/bookings/{first['id']}/cancel", json={})

        body = result.json()
        assert body["booking"]["status"] == "cancelled"
        assert body["promoted"]["id"] == second["id"]
        assert body["promoted"]["status"] == "booked"

    async def test_cancelling_a_waitlisted_booking_promotes_nobody(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """No seat was freed — the member was never occupying one."""
        session = await _session(staff, db, accounts, capacity=1)
        await _book(staff, session["id"], (await _member(staff))["id"])
        _, waiting = await _book(staff, session["id"], (await _member(staff))["id"])
        _, behind = await _book(staff, session["id"], (await _member(staff))["id"])

        result = await staff.post(f"/api/v1/bookings/{waiting['id']}/cancel", json={})

        assert result.json()["promoted"] is None
        after = (await staff.get(f"/api/v1/sessions/{session['id']}")).json()
        assert after["booked_count"] == 1
        del behind

    async def test_an_expired_member_is_skipped_not_promoted(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Promoting an expired member would be the outcome goal 4 blocks, reached
        by a side door. They keep their queue position and the timeline records why
        they were passed over."""
        session = await _session(staff, db, accounts, capacity=1)
        _, holder = await _book(staff, session["id"], (await _member(staff))["id"])
        expired = await _member(staff, expiry="2028-01-01")
        _, first_in_queue = await _book(staff, session["id"], expired["id"])
        _, next_in_queue = await _book(staff, session["id"], (await _member(staff))["id"])

        # Expire them after they joined the waitlist — which is the realistic case.
        await db.execute(
            text("UPDATE members SET membership_expiry = '2020-01-01' WHERE id = :id"),
            {"id": uuid.UUID(expired["id"])},
        )
        await db.commit()

        result = await staff.post(f"/api/v1/bookings/{holder['id']}/cancel", json={})

        assert result.json()["promoted"]["id"] == next_in_queue["id"]

        timeline = (await staff.get(f"/api/v1/bookings/{first_in_queue['id']}/timeline")).json()[
            "events"
        ]
        assert any("passed over" in (e["note"] or "") for e in timeline)
        assert timeline[-1]["is_system"] is True

    async def test_two_cancellations_promote_two_different_members(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The bug this design exists to prevent: promoting the same person twice
        and leaving a seat empty."""
        session = await _session(staff, db, accounts, capacity=2)
        _, a = await _book(staff, session["id"], (await _member(staff))["id"])
        _, b = await _book(staff, session["id"], (await _member(staff))["id"])
        _, w1 = await _book(staff, session["id"], (await _member(staff))["id"])
        _, w2 = await _book(staff, session["id"], (await _member(staff))["id"])

        first = (await staff.post(f"/api/v1/bookings/{a['id']}/cancel", json={})).json()
        second = (await staff.post(f"/api/v1/bookings/{b['id']}/cancel", json={})).json()

        assert first["promoted"]["id"] == w1["id"]
        assert second["promoted"]["id"] == w2["id"]

    async def test_cancelling_twice_is_rejected_with_a_reason(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])
        await staff.post(f"/api/v1/bookings/{booking['id']}/cancel", json={})

        again = await staff.post(f"/api/v1/bookings/{booking['id']}/cancel", json={})

        assert again.status_code == 422
        assert again.json()["code"] == "illegal_transition"
        assert "already Cancelled" in again.json()["message"]


# ----------------------------------------------------------------- settling


class TestSettlement:
    async def _started_session_with_booking(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """A booking on a session that has already started.

        Created in the future then moved into the past directly, because the API
        refuses to book onto a session that has begun — which is the rule under
        test elsewhere.
        """
        session = await _session(staff, db, accounts, capacity=5)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])
        await db.execute(
            text("UPDATE sessions SET starts_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": uuid.UUID(session["id"])},
        )
        await db.commit()
        return session, booking

    async def test_a_booked_booking_can_be_settled_as_attended(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        _, booking = await self._started_session_with_booking(staff, db, accounts)

        response = await staff.post(
            f"/api/v1/bookings/{booking['id']}/settle", json={"attended": True}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "attended"

    async def test_a_booked_booking_can_be_settled_as_no_show(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        _, booking = await self._started_session_with_booking(staff, db, accounts)

        response = await staff.post(
            f"/api/v1/bookings/{booking['id']}/settle", json={"attended": False}
        )

        assert response.json()["status"] == "no_show"

    async def test_settling_before_the_session_starts_is_rejected(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])

        response = await staff.post(
            f"/api/v1/bookings/{booking['id']}/settle", json={"attended": True}
        )

        assert response.status_code == 422
        assert "has not started yet" in response.json()["message"]

    async def test_a_waitlisted_booking_cannot_be_settled(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=1)
        await _book(staff, session["id"], (await _member(staff))["id"])
        _, waiting = await _book(staff, session["id"], (await _member(staff))["id"])
        await db.execute(
            text("UPDATE sessions SET starts_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": uuid.UUID(session["id"])},
        )
        await db.commit()

        response = await staff.post(
            f"/api/v1/bookings/{waiting['id']}/settle", json={"attended": True}
        )

        assert response.status_code == 422
        assert "this one is Waitlisted" in response.json()["message"]

    async def test_settling_twice_is_rejected(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        _, booking = await self._started_session_with_booking(staff, db, accounts)
        await staff.post(f"/api/v1/bookings/{booking['id']}/settle", json={"attended": True})

        again = await staff.post(
            f"/api/v1/bookings/{booking['id']}/settle", json={"attended": False}
        )

        assert again.status_code == 422
        assert "this one is Attended" in again.json()["message"]

    async def test_a_settled_booking_cannot_be_cancelled(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        _, booking = await self._started_session_with_booking(staff, db, accounts)
        await staff.post(f"/api/v1/bookings/{booking['id']}/settle", json={"attended": True})

        response = await staff.post(f"/api/v1/bookings/{booking['id']}/cancel", json={})

        assert response.status_code == 422
        assert "already Attended" in response.json()["message"]

    async def test_an_instructor_can_settle_their_own_session(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """The brief asks instructors to "record who actually showed up"."""
        _, booking = await self._started_session_with_booking(staff, db, accounts)

        response = await instructor.post(
            f"/api/v1/bookings/{booking['id']}/settle", json={"attended": True}
        )

        assert response.status_code == 200

    async def test_an_instructor_cannot_settle_someone_elses_session(
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
            {"id": other, "e": f"other-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.commit()
        session = await _session(staff, db, accounts, capacity=5, instructor_id=str(other))
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])
        await db.execute(
            text("UPDATE sessions SET starts_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": uuid.UUID(session["id"])},
        )
        await db.commit()

        response = await instructor.post(
            f"/api/v1/bookings/{booking['id']}/settle", json={"attended": True}
        )

        assert response.status_code == 403


# ----------------------------------------------------------------- timeline


class TestTimeline:
    async def test_the_booking_travels_with_its_events(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A history has to say whose it is.

        The endpoint returns the booking alongside its entries because an entry
        reading ``waitlisted -> booked`` is meaningless without the member and the
        session it belongs to — and there is no endpoint that fetches one booking
        by id, so a caller has no second way to find out.
        """
        session = await _session(staff, db, accounts)
        member = await _member(staff)
        _, booking = await _book(staff, session["id"], member["id"])

        body = (await staff.get(f"/api/v1/bookings/{booking['id']}/timeline")).json()

        assert body["id"] == booking["id"]
        assert body["session_id"] == session["id"]
        assert body["status"] == "booked"
        assert body["member"]["id"] == member["id"]
        assert body["member"]["full_name"] == member["full_name"]
        # The expiry comes along too: a history is where a disputed booking gets
        # read, and whether the membership was valid is the first question asked.
        assert body["member"]["membership_expiry"] == member["membership_expiry"]
        assert isinstance(body["events"], list)

    async def test_creation_is_recorded(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])

        timeline = (await staff.get(f"/api/v1/bookings/{booking['id']}/timeline")).json()["events"]

        assert len(timeline) == 1
        assert timeline[0]["event_type"] == "created"
        assert timeline[0]["new_status"] == "booked"
        assert timeline[0]["actor_name"] == "Staff"

    async def test_every_status_change_records_old_and_new_and_who(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 9 names all three: old status, new status, and who made it."""
        session = await _session(staff, db, accounts)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])

        await staff.post(f"/api/v1/bookings/{booking['id']}/cancel", json={})

        timeline = (await staff.get(f"/api/v1/bookings/{booking['id']}/timeline")).json()["events"]
        change = timeline[-1]
        assert change["event_type"] == "status_changed"
        assert change["old_status"] == "booked"
        assert change["new_status"] == "cancelled"
        assert change["actor_name"] == "Staff"
        assert change["is_system"] is False

    async def test_an_automatic_promotion_is_marked_as_a_system_action(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Recording the staff member who cancelled as though they promoted this
        person would be a small lie in an audit log."""
        session = await _session(staff, db, accounts, capacity=1)
        _, holder = await _book(staff, session["id"], (await _member(staff))["id"])
        _, waiting = await _book(staff, session["id"], (await _member(staff))["id"])

        await staff.post(f"/api/v1/bookings/{holder['id']}/cancel", json={})

        timeline = (await staff.get(f"/api/v1/bookings/{waiting['id']}/timeline")).json()["events"]
        promotion = timeline[-1]
        assert promotion["is_system"] is True
        assert promotion["actor_name"] is None
        assert promotion["old_status"] == "waitlisted"
        assert promotion["new_status"] == "booked"
        assert "after a cancellation" in promotion["note"]

    async def test_notes_are_appended_not_overwritten(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])

        await staff.post(f"/api/v1/bookings/{booking['id']}/notes", json={"note": "Called ahead"})
        await staff.post(f"/api/v1/bookings/{booking['id']}/notes", json={"note": "Running late"})

        timeline = (await staff.get(f"/api/v1/bookings/{booking['id']}/timeline")).json()["events"]
        notes = [e["note"] for e in timeline if e["event_type"] == "note_added"]
        assert notes == ["Called ahead", "Running late"]

    async def test_the_timeline_is_ordered_by_identity_not_timestamp(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Two events written in one transaction share an occurred_at. Ordering by
        time would let a cancellation appear after the promotion it caused."""
        session = await _session(staff, db, accounts, capacity=1)
        _, holder = await _book(staff, session["id"], (await _member(staff))["id"])
        await staff.post(f"/api/v1/bookings/{holder['id']}/cancel", json={})

        timeline = (await staff.get(f"/api/v1/bookings/{holder['id']}/timeline")).json()["events"]

        assert [e["id"] for e in timeline] == sorted(e["id"] for e in timeline)
        assert timeline[0]["event_type"] == "created"

    async def test_there_is_no_way_to_edit_or_delete_an_entry(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 9: "Nothing in this timeline can be edited or deleted after the
        fact, including by studio staff." No such endpoint exists at any level, and
        the database rejects the operation regardless of who attempts it."""
        session = await _session(staff, db, accounts)
        _, booking = await _book(staff, session["id"], (await _member(staff))["id"])
        path = f"/api/v1/bookings/{booking['id']}/timeline"

        assert (await staff.request("DELETE", path)).status_code == 405
        assert (await staff.request("PATCH", path, json={})).status_code == 405
        assert (await staff.request("PUT", path, json={})).status_code == 405

        with pytest.raises(Exception, match="append-only"):
            await db.execute(text("UPDATE booking_events SET note = 'tampered'"))
        await db.rollback()
