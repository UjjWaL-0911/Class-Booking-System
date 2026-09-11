"""Session and co-instructor tests (goals 3 and 5).

The visibility tests are the important ones. Goal 1 requires an instructor to see
only their own sessions and says so must be enforced on the server, so each of
those calls the API with an instructor token and asserts on what came back — not on
what a UI would have rendered.
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

# Far enough out that "has this session started" is never ambiguous.
FUTURE = dt.date(2027, 3, 2)


async def _room(staff: AsyncClient) -> str:
    response = await staff.post("/api/v1/rooms", json={"name": f"Studio {uuid.uuid4().hex[:8]}"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _class(staff: AsyncClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "title": f"Vinyasa {uuid.uuid4().hex[:6]}",
        "description": "",
        "discipline": "yoga",
        "default_duration_min": 60,
        "default_capacity": 20,
        **overrides,
    }
    response = await staff.post("/api/v1/classes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _user_id(db: AsyncSession, email: str) -> str:
    row = (
        await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    ).scalar_one()
    return str(row)


async def _make_instructor(db: AsyncSession, name: str = "Extra") -> str:
    """A second instructor, for co-instructor and visibility tests."""
    tag = uuid.uuid4().hex[:8]
    user_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, full_name, role) "
            "VALUES (:id, :e, 'x', :n, 'instructor')"
        ),
        {"id": user_id, "e": f"{name.lower()}-{tag}@example.com", "n": name},
    )
    await db.commit()
    return str(user_id)


async def _session(
    staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "class_id": (await _class(staff))["id"],
        "session_date": FUTURE.isoformat(),
        "start_time": "18:00:00",
        "primary_instructor_id": await _user_id(db, accounts["instructor"]),
        "room_id": await _room(staff),
        **overrides,
    }
    response = await staff.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    async def test_duration_and_capacity_default_from_the_class(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff, default_duration_min=45, default_capacity=12)

        body = await _session(staff, db, accounts, class_id=studio_class["id"])

        assert body["duration_min"] == 45
        assert body["capacity"] == 12

    async def test_both_can_be_overridden_per_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 3 requires the defaults to be overridable per session."""
        body = await _session(staff, db, accounts, duration_min=90, capacity=5)

        assert body["duration_min"] == 90
        assert body["capacity"] == 5

    async def test_defaults_are_copied_not_referenced(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Editing the class later must not move sessions already scheduled."""
        studio_class = await _class(staff, default_capacity=20)
        session = await _session(staff, db, accounts, class_id=studio_class["id"])

        await staff.patch(
            f"/api/v1/classes/{studio_class['id']}",
            json={"version": studio_class["version"], "default_capacity": 99},
        )

        after = (await staff.get(f"/api/v1/sessions/{session['id']}")).json()
        assert after["capacity"] == 20

    async def test_ends_at_is_derived_from_the_duration(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        body = await _session(staff, db, accounts, duration_min=75)

        starts = dt.datetime.fromisoformat(body["starts_at"])
        ends = dt.datetime.fromisoformat(body["ends_at"])
        assert ends - starts == dt.timedelta(minutes=75)

    async def test_local_time_survives_the_round_trip(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Staff type wall-clock time; the store is UTC. What comes back must be
        the time they typed, or the schedule is wrong for half the year."""
        body = await _session(staff, db, accounts, start_time="18:30:00")

        assert body["start_time"] == "18:30:00"
        assert body["session_date"] == FUTURE.isoformat()

    async def test_a_session_cannot_be_added_to_an_archived_class(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        await staff.post(f"/api/v1/classes/{studio_class['id']}/archive")

        response = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": studio_class["id"],
                "session_date": FUTURE.isoformat(),
                "start_time": "18:00:00",
                "primary_instructor_id": await _user_id(db, accounts["instructor"]),
                "room_id": await _room(staff),
            },
        )

        assert response.status_code == 422
        assert "archived" in response.json()["message"]

    async def test_an_instructor_cannot_schedule_a_session(
        self,
        instructor: AsyncClient,
        staff: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        response = await instructor.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": FUTURE.isoformat(),
                "start_time": "18:00:00",
                "primary_instructor_id": await _user_id(db, accounts["instructor"]),
                "room_id": await _room(staff),
            },
        )

        assert response.status_code == 403


class TestOverlapConstraints:
    async def test_a_room_cannot_host_two_sessions_at_once(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Enforced by a GiST exclusion constraint, surfaced as a readable 409
        rather than a 500 with Postgres internals in it."""
        room_id = await _room(staff)
        await _session(staff, db, accounts, room_id=room_id, start_time="18:00:00")

        clash = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": FUTURE.isoformat(),
                "start_time": "18:30:00",
                "primary_instructor_id": await _make_instructor(db),
                "room_id": room_id,
            },
        )

        assert clash.status_code == 409
        assert clash.json()["code"] == "conflict"

    async def test_an_instructor_cannot_lead_two_sessions_at_once(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        instructor_id = await _user_id(db, accounts["instructor"])
        await _session(staff, db, accounts, start_time="18:00:00")

        clash = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": FUTURE.isoformat(),
                "start_time": "18:30:00",
                "primary_instructor_id": instructor_id,
                "room_id": await _room(staff),
            },
        )

        assert clash.status_code == 409

    async def test_back_to_back_sessions_are_allowed(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """tstzrange is half-open, so a class starting exactly when another ends
        does not overlap — which is how a studio actually runs."""
        room_id = await _room(staff)
        instructor_id = await _user_id(db, accounts["instructor"])
        await _session(
            staff,
            db,
            accounts,
            room_id=room_id,
            start_time="18:00:00",
            duration_min=60,
        )

        adjacent = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": FUTURE.isoformat(),
                "start_time": "19:00:00",
                "primary_instructor_id": instructor_id,
                "room_id": room_id,
            },
        )

        assert adjacent.status_code == 201


class TestVisibility:
    """Goal 5: "Every instructor can see one list of every session where they are
    the primary instructor or a co-instructor." The list endpoint *is* that list —
    the filter produces it, so there is no second route to the same answer."""

    async def test_an_instructor_sees_sessions_they_lead(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        studio_class = await _class(staff)
        mine = await _session(staff, db, accounts, class_id=studio_class["id"])

        listed = (await instructor.get(f"/api/v1/sessions?class_id={studio_class['id']}")).json()

        assert [s["id"] for s in listed["items"]] == [mine["id"]]

    async def test_an_instructor_does_not_see_other_peoples_sessions(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        studio_class = await _class(staff)
        other_id = await _make_instructor(db, "Someone")
        theirs = await _session(
            staff,
            db,
            accounts,
            class_id=studio_class["id"],
            primary_instructor_id=other_id,
        )

        listed = (await instructor.get(f"/api/v1/sessions?class_id={studio_class['id']}")).json()

        assert theirs["id"] not in [s["id"] for s in listed["items"]]
        assert listed["total"] == 0

    async def test_fetching_someone_elses_session_is_404_not_403(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """403 would confirm the session exists. The filter means the row is never
        selected, so "not found" is the honest answer as well as the safe one."""
        other_id = await _make_instructor(db, "Someone")
        theirs = await _session(staff, db, accounts, primary_instructor_id=other_id)

        response = await instructor.get(f"/api/v1/sessions/{theirs['id']}")

        assert response.status_code == 404

    async def test_adding_a_co_instructor_grants_visibility(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """The union half of the visibility rule."""
        other_id = await _make_instructor(db, "Someone")
        theirs = await _session(staff, db, accounts, primary_instructor_id=other_id)
        assert (await instructor.get(f"/api/v1/sessions/{theirs['id']}")).status_code == 404

        me = await _user_id(db, accounts["instructor"])
        await staff.post(f"/api/v1/sessions/{theirs['id']}/co-instructors", json={"user_id": me})

        assert (await instructor.get(f"/api/v1/sessions/{theirs['id']}")).status_code == 200

    async def test_removing_a_co_instructor_withdraws_visibility(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        other_id = await _make_instructor(db, "Someone")
        theirs = await _session(staff, db, accounts, primary_instructor_id=other_id)
        me = await _user_id(db, accounts["instructor"])
        await staff.post(f"/api/v1/sessions/{theirs['id']}/co-instructors", json={"user_id": me})

        await staff.delete(f"/api/v1/sessions/{theirs['id']}/co-instructors/{me}")

        assert (await instructor.get(f"/api/v1/sessions/{theirs['id']}")).status_code == 404

    async def test_staff_see_every_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        other_id = await _make_instructor(db, "Someone")
        theirs = await _session(
            staff,
            db,
            accounts,
            class_id=studio_class["id"],
            primary_instructor_id=other_id,
        )

        # Scoped to this test's own class: the suite shares a database, so an
        # unfiltered list would depend on how many sessions ran before it.
        listed = (await staff.get(f"/api/v1/sessions?class_id={studio_class['id']}")).json()

        assert theirs["id"] in [s["id"] for s in listed["items"]]


class TestCoInstructors:
    async def test_one_instructor_can_co_instruct_overlapping_sessions(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 5 explicitly allows this, which is why the exclusion constraint
        covers only the *primary* instructor."""
        helper = await _make_instructor(db, "Helper")
        first = await _session(staff, db, accounts, start_time="18:00:00")
        second = await _session(
            staff,
            db,
            accounts,
            start_time="18:00:00",
            primary_instructor_id=await _make_instructor(db, "Other"),
        )

        one = await staff.post(
            f"/api/v1/sessions/{first['id']}/co-instructors",
            json={"user_id": helper},
        )
        two = await staff.post(
            f"/api/v1/sessions/{second['id']}/co-instructors",
            json={"user_id": helper},
        )

        assert one.status_code == 200
        assert two.status_code == 200

    async def test_the_primary_instructor_cannot_also_be_a_co_instructor(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        primary = session["primary_instructor"]["id"]

        response = await staff.post(
            f"/api/v1/sessions/{session['id']}/co-instructors",
            json={"user_id": primary},
        )

        assert response.status_code == 422

    async def test_adding_the_same_co_instructor_twice_is_rejected(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        helper = await _make_instructor(db, "Helper")
        await staff.post(
            f"/api/v1/sessions/{session['id']}/co-instructors",
            json={"user_id": helper},
        )

        again = await staff.post(
            f"/api/v1/sessions/{session['id']}/co-instructors",
            json={"user_id": helper},
        )

        assert again.status_code == 422

    async def test_only_staff_can_add_a_co_instructor(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """Goal 5 is explicit: "Only studio staff can add or remove a
        co-instructor" — including on a session the instructor leads themselves."""
        session = await _session(staff, db, accounts)
        helper = await _make_instructor(db, "Helper")

        response = await instructor.post(
            f"/api/v1/sessions/{session['id']}/co-instructors",
            json={"user_id": helper},
        )

        assert response.status_code == 403

    async def test_only_staff_can_remove_a_co_instructor(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        session = await _session(staff, db, accounts)
        helper = await _make_instructor(db, "Helper")
        await staff.post(
            f"/api/v1/sessions/{session['id']}/co-instructors",
            json={"user_id": helper},
        )

        response = await instructor.delete(
            f"/api/v1/sessions/{session['id']}/co-instructors/{helper}"
        )

        assert response.status_code == 403


class TestListingByClass:
    async def test_opening_a_class_shows_its_sessions(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The last sentence of goal 3."""
        studio_class = await _class(staff)
        first = await _session(
            staff, db, accounts, class_id=studio_class["id"], start_time="09:00:00"
        )
        second = await _session(
            staff, db, accounts, class_id=studio_class["id"], start_time="11:00:00"
        )
        await _session(staff, db, accounts)  # a different class

        listed = (await staff.get(f"/api/v1/sessions?class_id={studio_class['id']}")).json()

        assert listed["total"] == 2
        assert {s["id"] for s in listed["items"]} == {first["id"], second["id"]}

    async def test_sessions_are_ordered_by_start_time(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        later = await _session(
            staff, db, accounts, class_id=studio_class["id"], start_time="17:00:00"
        )
        earlier = await _session(
            staff, db, accounts, class_id=studio_class["id"], start_time="09:00:00"
        )

        listed = (await staff.get(f"/api/v1/sessions?class_id={studio_class['id']}")).json()

        assert [s["id"] for s in listed["items"]] == [earlier["id"], later["id"]]

    async def test_archiving_a_class_hides_its_sessions_by_default(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        session = await _session(staff, db, accounts, class_id=studio_class["id"])
        await staff.post(f"/api/v1/classes/{studio_class['id']}/archive")

        scope = f"class_id={studio_class['id']}"
        hidden = (await staff.get(f"/api/v1/sessions?{scope}")).json()
        shown = (await staff.get(f"/api/v1/sessions?{scope}&include_archived_classes=true")).json()

        assert session["id"] not in [s["id"] for s in hidden["items"]]
        assert session["id"] in [s["id"] for s in shown["items"]]


class TestUpdate:
    async def test_staff_can_move_a_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, start_time="18:00:00")

        response = await staff.patch(
            f"/api/v1/sessions/{session['id']}",
            json={"version": session["version"], "start_time": "19:30:00"},
        )

        assert response.status_code == 200
        assert response.json()["start_time"] == "19:30:00"

    async def test_a_stale_version_is_rejected(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        stale = session["version"]
        await staff.patch(
            f"/api/v1/sessions/{session['id']}",
            json={"version": stale, "capacity": 15},
        )

        second = await staff.patch(
            f"/api/v1/sessions/{session['id']}",
            json={"version": stale, "capacity": 16},
        )

        assert second.status_code == 409

    async def test_capacity_cannot_be_reduced_below_the_booked_count(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """No database constraint catches this — the capacity trigger fires on
        writes to bookings, not to sessions — so refusing it here is the only thing
        standing between staff and a silently oversold session."""
        session = await _session(staff, db, accounts, capacity=10)
        actor = await _user_id(db, accounts["staff"])
        for i in range(3):
            member = uuid.uuid4()
            await db.execute(
                text(
                    "INSERT INTO members (id, full_name, email, membership_expiry) "
                    "VALUES (:id, :n, :e, '2027-01-01')"
                ),
                {"id": member, "n": f"M{i}", "e": f"m{i}-{uuid.uuid4().hex[:8]}@x.com"},
            )
            await db.execute(
                text(
                    "INSERT INTO bookings (session_id, member_id, status, created_by) "
                    "VALUES (:s, :m, 'booked', :u)"
                ),
                {"s": uuid.UUID(session["id"]), "m": member, "u": uuid.UUID(actor)},
            )
        await db.commit()

        response = await staff.patch(
            f"/api/v1/sessions/{session['id']}",
            json={"version": session["version"], "capacity": 2},
        )

        assert response.status_code == 409
        assert "3 members are booked" in response.json()["message"]

    async def test_capacity_can_be_reduced_to_the_booked_count(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=10)

        response = await staff.patch(
            f"/api/v1/sessions/{session['id']}",
            json={"version": session["version"], "capacity": 1},
        )

        assert response.status_code == 200


class TestDelete:
    async def test_deleting_hides_the_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)

        assert (await staff.delete(f"/api/v1/sessions/{session['id']}")).status_code == 204

        assert (await staff.get(f"/api/v1/sessions/{session['id']}")).status_code == 404

    async def test_the_row_survives_and_bookings_are_cancelled_with_a_trail(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 9 does not allow history to disappear because something was removed
        from the schedule, and it does not allow a booking to change state without
        a record of why."""
        session = await _session(staff, db, accounts)
        session_uuid = uuid.UUID(session["id"])
        actor = uuid.UUID(await _user_id(db, accounts["staff"]))
        member = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO members (id, full_name, email, membership_expiry) "
                "VALUES (:id, 'Ada', :e, '2027-01-01')"
            ),
            {"id": member, "e": f"ada-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.execute(
            text(
                "INSERT INTO bookings (session_id, member_id, status, created_by) "
                "VALUES (:s, :m, 'booked', :u)"
            ),
            {"s": session_uuid, "m": member, "u": actor},
        )
        await db.commit()

        await staff.delete(f"/api/v1/sessions/{session['id']}")

        row = (
            await db.execute(
                text("SELECT deleted_at IS NOT NULL FROM sessions WHERE id = :s"),
                {"s": session_uuid},
            )
        ).scalar_one()
        status_after = (
            await db.execute(
                text("SELECT status FROM bookings WHERE session_id = :s"),
                {"s": session_uuid},
            )
        ).scalar_one()
        event = (
            await db.execute(
                text(
                    "SELECT note, is_system, old_status, new_status "
                    "FROM booking_events e JOIN bookings b ON b.id = e.booking_id "
                    "WHERE b.session_id = :s"
                ),
                {"s": session_uuid},
            )
        ).one()

        assert row is True  # soft-deleted, not gone
        assert status_after == "cancelled"
        assert event.note == "Session was deleted."
        assert event.is_system is True
        assert (event.old_status, event.new_status) == ("booked", "cancelled")

    async def test_deleting_frees_the_room_slot(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The exclusion constraints are partial on deleted_at IS NULL, so a
        removed session must not keep blocking the time it used to occupy."""
        room_id = await _room(staff)
        session = await _session(staff, db, accounts, room_id=room_id)

        await staff.delete(f"/api/v1/sessions/{session['id']}")

        replacement = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": (await _class(staff))["id"],
                "session_date": FUTURE.isoformat(),
                "start_time": "18:00:00",
                "primary_instructor_id": await _make_instructor(db),
                "room_id": room_id,
            },
        )
        assert replacement.status_code == 201

    async def test_an_instructor_cannot_delete_a_session(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        session = await _session(staff, db, accounts)

        response = await instructor.delete(f"/api/v1/sessions/{session['id']}")

        assert response.status_code == 403
