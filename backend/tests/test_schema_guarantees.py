"""The guarantees the database enforces on its own.

Each test here corresponds to a rule that must hold no matter which code path runs —
including one written later that forgets to check. They run against the real
migrated schema, because every mechanism under test (partial unique indexes, GiST
exclusion constraints, deferrable constraint triggers, statement triggers) exists
only in PostgreSQL.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import build_engine, build_session_factory
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.usefixtures("migrated_schema")

NOW = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC)


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = build_engine(url=TEST_DATABASE_URL)
    factory = build_session_factory(engine)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _seed(db: AsyncSession) -> dict[str, uuid.UUID]:
    """One room, one instructor, one class, one 2-seat session, two members."""
    ids = {k: uuid.uuid4() for k in ("room", "user", "cls", "session", "m1", "m2")}
    tag = ids["room"].hex[:8]

    await db.execute(
        text("INSERT INTO rooms (id, name) VALUES (:id, :name)"),
        {"id": ids["room"], "name": f"Studio {tag}"},
    )
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, full_name, role) "
            "VALUES (:id, :email, 'x', 'Priya', 'instructor')"
        ),
        {"id": ids["user"], "email": f"priya-{tag}@example.com"},
    )
    await db.execute(
        text(
            "INSERT INTO classes (id, title, discipline, default_duration_min, "
            "default_capacity) VALUES (:id, :title, 'yoga', 60, 20)"
        ),
        # Tagged like the email above, and for the same reason: live class titles
        # are unique, and this database is never truncated between runs.
        {"id": ids["cls"], "title": f"Vinyasa Flow {tag}"},
    )
    await db.execute(
        text(
            "INSERT INTO sessions (id, class_id, starts_at, primary_instructor_id, "
            "room_id, duration_min, capacity) "
            "VALUES (:id, :cls, :starts, :user, :room, 60, 2)"
        ),
        {
            "id": ids["session"],
            "cls": ids["cls"],
            "starts": NOW,
            "user": ids["user"],
            "room": ids["room"],
        },
    )
    for key, name in (("m1", "Ada"), ("m2", "Grace")):
        await db.execute(
            text(
                "INSERT INTO members (id, full_name, email, membership_expiry) "
                "VALUES (:id, :name, :email, :expiry)"
            ),
            {
                "id": ids[key],
                "name": name,
                "email": f"{name.lower()}-{tag}@example.com",
                "expiry": dt.date(2027, 1, 1),
            },
        )
    await db.commit()
    return ids


async def _book(db: AsyncSession, ids: dict[str, uuid.UUID], member: str, status: str) -> None:
    await db.execute(
        text(
            "INSERT INTO bookings (session_id, member_id, status, created_by) "
            "VALUES (:s, :m, CAST(:st AS booking_status), :u)"
        ),
        {"s": ids["session"], "m": ids[member], "st": status, "u": ids["user"]},
    )


class TestDerivedColumns:
    async def test_ends_at_is_computed_from_duration(self, db: AsyncSession) -> None:
        ids = await _seed(db)
        ends = (
            await db.execute(
                text("SELECT ends_at FROM sessions WHERE id = :id"), {"id": ids["session"]}
            )
        ).scalar_one()

        assert ends == NOW + dt.timedelta(minutes=60)

    async def test_ends_at_cannot_be_set_directly(self, db: AsyncSession) -> None:
        """The trigger fires on every UPDATE, not only when its inputs change.

        Without that, an UPDATE writing ends_at directly would desynchronise the
        column from the data it is derived from — and with it the GiST index that
        the overlap constraints depend on.
        """
        ids = await _seed(db)
        await db.execute(
            text("UPDATE sessions SET ends_at = :bogus WHERE id = :id"),
            {"bogus": NOW + dt.timedelta(days=99), "id": ids["session"]},
        )
        ends = (
            await db.execute(
                text("SELECT ends_at FROM sessions WHERE id = :id"), {"id": ids["session"]}
            )
        ).scalar_one()

        assert ends == NOW + dt.timedelta(minutes=60)

    async def test_updated_at_moves_on_update(self, db: AsyncSession) -> None:
        ids = await _seed(db)
        before = (
            await db.execute(
                text("SELECT updated_at FROM classes WHERE id = :id"), {"id": ids["cls"]}
            )
        ).scalar_one()

        await db.execute(
            text("UPDATE classes SET title = :title WHERE id = :id"),
            {"id": ids["cls"], "title": f"Renamed {ids['cls'].hex[:8]}"},
        )
        after = (
            await db.execute(
                text("SELECT updated_at FROM classes WHERE id = :id"), {"id": ids["cls"]}
            )
        ).scalar_one()

        assert after > before


class TestOverlapConstraints:
    async def test_room_cannot_be_double_booked(self, db: AsyncSession) -> None:
        ids = await _seed(db)
        other_instructor = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :email, 'x', 'Sam', 'instructor')"
            ),
            {"id": other_instructor, "email": f"sam-{other_instructor.hex[:8]}@example.com"},
        )

        with pytest.raises(IntegrityError) as exc:
            await db.execute(
                text(
                    "INSERT INTO sessions (class_id, starts_at, primary_instructor_id, "
                    "room_id, duration_min, capacity) "
                    "VALUES (:cls, :starts, :user, :room, 60, 10)"
                ),
                {
                    "cls": ids["cls"],
                    "starts": NOW + dt.timedelta(minutes=30),  # overlaps
                    "user": other_instructor,
                    "room": ids["room"],
                },
            )
        assert "no_room_overlap" in str(exc.value)

    async def test_primary_instructor_cannot_be_double_booked(self, db: AsyncSession) -> None:
        ids = await _seed(db)
        other_room = uuid.uuid4()
        await db.execute(
            text("INSERT INTO rooms (id, name) VALUES (:id, :name)"),
            {"id": other_room, "name": f"Studio {other_room.hex[:8]}"},
        )

        with pytest.raises(IntegrityError) as exc:
            await db.execute(
                text(
                    "INSERT INTO sessions (class_id, starts_at, primary_instructor_id, "
                    "room_id, duration_min, capacity) "
                    "VALUES (:cls, :starts, :user, :room, 60, 10)"
                ),
                {
                    "cls": ids["cls"],
                    "starts": NOW + dt.timedelta(minutes=30),
                    "user": ids["user"],
                    "room": other_room,
                },
            )
        assert "no_primary_instructor_overlap" in str(exc.value)

    async def test_adjacent_sessions_are_allowed(self, db: AsyncSession) -> None:
        """tstzrange is half-open, so a session starting exactly when another ends
        does not overlap — back-to-back classes in one room are normal."""
        ids = await _seed(db)
        await db.execute(
            text(
                "INSERT INTO sessions (class_id, starts_at, primary_instructor_id, "
                "room_id, duration_min, capacity) "
                "VALUES (:cls, :starts, :user, :room, 60, 10)"
            ),
            {
                "cls": ids["cls"],
                "starts": NOW + dt.timedelta(minutes=60),
                "user": ids["user"],
                "room": ids["room"],
            },
        )
        await db.commit()

    async def test_soft_deleted_sessions_are_exempt(self, db: AsyncSession) -> None:
        """The constraints are partial on deleted_at IS NULL, so a deleted session
        does not block the slot it used to occupy."""
        ids = await _seed(db)
        await db.execute(
            text("UPDATE sessions SET deleted_at = now() WHERE id = :id"),
            {"id": ids["session"]},
        )
        await db.execute(
            text(
                "INSERT INTO sessions (class_id, starts_at, primary_instructor_id, "
                "room_id, duration_min, capacity) "
                "VALUES (:cls, :starts, :user, :room, 60, 10)"
            ),
            {
                "cls": ids["cls"],
                "starts": NOW,
                "user": ids["user"],
                "room": ids["room"],
            },
        )
        await db.commit()


class TestOneActiveBooking:
    async def test_a_member_cannot_hold_two_places_on_one_session(self, db: AsyncSession) -> None:
        """Also what turns a double-submitted booking into a clean 409."""
        ids = await _seed(db)
        await _book(db, ids, "m1", "booked")

        with pytest.raises(IntegrityError) as exc:
            await _book(db, ids, "m1", "waitlisted")
        assert "one_active_booking" in str(exc.value)

    async def test_a_cancelled_member_can_book_again(self, db: AsyncSession) -> None:
        """The index is partial on the two active statuses precisely so that
        cancelling and rebooking is possible."""
        ids = await _seed(db)
        await _book(db, ids, "m1", "cancelled")
        await _book(db, ids, "m1", "booked")
        await db.commit()


class TestCapacityBackstop:
    async def test_oversell_is_rejected_at_commit(self, db: AsyncSession) -> None:
        """The trigger is DEFERRABLE INITIALLY DEFERRED, so it fires at COMMIT
        rather than at INSERT — and it takes the session lock itself, which is what
        makes it race-safe rather than merely a single-threaded sanity check."""
        ids = await _seed(db)  # capacity 2
        await _book(db, ids, "m1", "booked")
        await _book(db, ids, "m2", "booked")
        await db.commit()  # exactly at capacity: fine

        third = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO members (id, full_name, email, membership_expiry) "
                "VALUES (:id, 'Kay', :email, :e)"
            ),
            {"id": third, "email": f"kay-{third.hex[:8]}@example.com", "e": dt.date(2027, 1, 1)},
        )
        await db.execute(
            text(
                "INSERT INTO bookings (session_id, member_id, status, created_by) "
                "VALUES (:s, :m, 'booked', :u)"
            ),
            {"s": ids["session"], "m": third, "u": ids["user"]},
        )

        with pytest.raises(DBAPIError) as exc:
            await db.commit()
        assert "oversold" in str(exc.value)

    async def test_waitlisting_beyond_capacity_is_allowed(self, db: AsyncSession) -> None:
        """The WHEN clause keeps the trigger off every transition that is not a move
        into 'booked' — a full session must still accept waitlist entries."""
        ids = await _seed(db)
        await _book(db, ids, "m1", "booked")
        await _book(db, ids, "m2", "waitlisted")
        await db.commit()


class TestAppendOnlyTimeline:
    async def _one_event(self, db: AsyncSession, ids: dict[str, uuid.UUID]) -> None:
        await _book(db, ids, "m1", "booked")
        await db.execute(
            text(
                "INSERT INTO booking_events (booking_id, event_type, new_status, "
                "actor_user_id) SELECT id, 'created', 'booked', :u FROM bookings "
                "WHERE session_id = :s"
            ),
            {"u": ids["user"], "s": ids["session"]},
        )
        await db.commit()

    async def test_update_is_rejected(self, db: AsyncSession) -> None:
        ids = await _seed(db)
        await self._one_event(db, ids)

        with pytest.raises(DBAPIError) as exc:
            await db.execute(text("UPDATE booking_events SET note = 'tampered'"))
        assert "append-only" in str(exc.value)

    async def test_delete_is_rejected(self, db: AsyncSession) -> None:
        ids = await _seed(db)
        await self._one_event(db, ids)

        with pytest.raises(DBAPIError) as exc:
            await db.execute(text("DELETE FROM booking_events"))
        assert "append-only" in str(exc.value)

    async def test_truncate_is_rejected(self, db: AsyncSession) -> None:
        """Row-level triggers do not fire on TRUNCATE, which would otherwise empty
        an append-only table in one statement. The separate BEFORE TRUNCATE
        statement trigger is what closes that."""
        ids = await _seed(db)
        await self._one_event(db, ids)

        with pytest.raises(DBAPIError) as exc:
            await db.execute(text("TRUNCATE booking_events"))
        assert "append-only" in str(exc.value)


class TestAlertDismissalReset:
    async def test_changing_the_expiry_clears_dismissals(self, db: AsyncSession) -> None:
        """Closes the case that value-matching alone misses: dismiss, extend the
        expiry, then correct it back to the original date — where the old row would
        match again and suppress an alert for a genuinely expired member."""
        ids = await _seed(db)
        original = dt.date(2027, 1, 1)

        await db.execute(
            text(
                "INSERT INTO membership_alert_dismissals "
                "(member_id, dismissed_expiry, dismissed_by) VALUES (:m, :e, :u)"
            ),
            {"m": ids["m1"], "e": original, "u": ids["user"]},
        )
        await db.commit()

        await db.execute(
            text("UPDATE members SET membership_expiry = :e WHERE id = :id"),
            {"e": dt.date(2027, 6, 1), "id": ids["m1"]},
        )
        await db.commit()

        remaining = (
            await db.execute(
                text("SELECT count(*) FROM membership_alert_dismissals WHERE member_id = :m"),
                {"m": ids["m1"]},
            )
        ).scalar_one()
        assert remaining == 0

    async def test_an_unrelated_update_keeps_the_dismissal(self, db: AsyncSession) -> None:
        """The WHEN clause means only a genuine expiry change resets the alert;
        renaming a member must not un-dismiss it."""
        ids = await _seed(db)
        await db.execute(
            text(
                "INSERT INTO membership_alert_dismissals "
                "(member_id, dismissed_expiry, dismissed_by) VALUES (:m, :e, :u)"
            ),
            {"m": ids["m1"], "e": dt.date(2027, 1, 1), "u": ids["user"]},
        )
        await db.commit()

        await db.execute(
            text("UPDATE members SET full_name = 'Ada L' WHERE id = :id"),
            {"id": ids["m1"]},
        )
        await db.commit()

        remaining = (
            await db.execute(
                text("SELECT count(*) FROM membership_alert_dismissals WHERE member_id = :m"),
                {"m": ids["m1"]},
            )
        ).scalar_one()
        assert remaining == 1
