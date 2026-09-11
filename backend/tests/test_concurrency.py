"""Concurrency tests.

These are the tests the whole locking design exists for, and the only ones that can
actually falsify it. Everything else in the suite runs one request at a time, where
a missing lock is invisible.

Each test runs N genuinely parallel transactions — separate sessions on separate
connections, gathered with ``asyncio.gather`` — against real PostgreSQL. That is not
incidental:

* A single ``AsyncSession`` cannot execute concurrently; asyncpg raises
  ``InterfaceError: another operation is in progress``. Sharing one would silently
  serialise the test and prove nothing.
* SQLite has no ``SELECT ... FOR UPDATE``, no GiST exclusion constraints and no
  deferrable constraint triggers, so none of this is testable there.

The pool is sized per test, because the production pool is deliberately small and
twenty parallel bookings genuinely need twenty connections.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.errors import DomainError, IllegalTransition
from app.db.engine import build_engine, build_session_factory
from app.models.enums import BookingStatus
from app.models.user import User
from app.services.booking_service import BookingService
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.usefixtures("migrated_schema")

T = TypeVar("T")

FUTURE = dt.datetime(2027, 8, 3, 18, 0, tzinfo=dt.UTC)


@pytest.fixture
async def engine() -> AsyncEngine:
    """An engine with room for real parallelism.

    Production runs pool_size=5 on a 512 MB instance. These tests need more
    connections than that by design — the point is to have twenty transactions
    contending at once.
    """
    eng = build_engine(url=TEST_DATABASE_URL, pool_size=30, max_overflow=10)
    yield eng
    await eng.dispose()


class Fixture:
    """Ids for one isolated scenario."""

    def __init__(self, session_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self.session_id = session_id
        self.actor_id = actor_id
        self.members: list[uuid.UUID] = []


async def _scenario(db: AsyncSession, *, capacity: int, members: int) -> Fixture:
    """Build a session with a given capacity and a pool of valid members."""
    tag = uuid.uuid4().hex[:8]
    ids = {k: uuid.uuid4() for k in ("room", "user", "cls", "session")}

    await db.execute(
        text("INSERT INTO rooms (id, name) VALUES (:id, :n)"),
        {"id": ids["room"], "n": f"Studio {tag}"},
    )
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, full_name, role) "
            "VALUES (:id, :e, 'x', 'Staff', 'staff')"
        ),
        {"id": ids["user"], "e": f"staff-{tag}@example.com"},
    )
    await db.execute(
        text(
            "INSERT INTO classes (id, title, discipline, default_duration_min, "
            "default_capacity) VALUES (:id, :t, 'yoga', 60, :c)"
        ),
        {"id": ids["cls"], "t": f"Class {tag}", "c": capacity},
    )
    await db.execute(
        text(
            "INSERT INTO sessions (id, class_id, starts_at, primary_instructor_id, "
            "room_id, duration_min, capacity) "
            "VALUES (:id, :c, :s, :u, :r, 60, :cap)"
        ),
        {
            "id": ids["session"],
            "c": ids["cls"],
            "s": FUTURE,
            "u": ids["user"],
            "r": ids["room"],
            "cap": capacity,
        },
    )

    fixture = Fixture(ids["session"], ids["user"])
    for i in range(members):
        member_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO members (id, full_name, email, membership_expiry) "
                "VALUES (:id, :n, :e, '2030-01-01')"
            ),
            {"id": member_id, "n": f"M{i}", "e": f"m{i}-{tag}@example.com"},
        )
        fixture.members.append(member_id)
    await db.commit()
    return fixture


async def _in_own_transaction(
    engine: AsyncEngine, work: Callable[[AsyncSession, User], Awaitable[T]]
) -> T | DomainError:
    """Run ``work`` in its own session, connection and transaction.

    Domain errors are returned rather than raised so ``gather`` can report every
    outcome — losing a race is an expected result here, not a test failure.
    """
    factory = build_session_factory(engine)
    async with factory() as db:
        actor = (
            await db.execute(text("SELECT id, role FROM users WHERE role = 'staff' LIMIT 1"))
        ).one()
        user = await db.get(User, actor.id)
        assert user is not None
        try:
            result = await work(db, user)
            await db.commit()
            return result
        except DomainError as exc:
            await db.rollback()
            return exc


async def _booked_count(db: AsyncSession, session_id: uuid.UUID) -> int:
    return (
        await db.execute(
            text("SELECT count(*) FROM bookings WHERE session_id = :s AND status = 'booked'"),
            {"s": session_id},
        )
    ).scalar_one()


async def _statuses(db: AsyncSession, session_id: uuid.UUID) -> dict[str, int]:
    rows = (
        await db.execute(
            text("SELECT status, count(*) FROM bookings WHERE session_id = :s GROUP BY status"),
            {"s": session_id},
        )
    ).all()
    return {row[0]: row[1] for row in rows}


@pytest.mark.concurrency
class TestLastSeat:
    async def test_twenty_simultaneous_bookings_for_one_seat(
        self, db: AsyncSession, engine: AsyncEngine
    ) -> None:
        """The scenario the brief opens with: "Two members claim the last open spot
        in the same class within minutes of each other."

        Twenty transactions race for a single seat. Exactly one may be Booked. If
        the session row lock were missing, several would each read booked=0 and
        each decide there was room.
        """
        scenario = await _scenario(db, capacity=1, members=20)
        settings = get_settings()

        async def book(member_id: uuid.UUID) -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str:
                booking = await BookingService(session_db, settings).create(
                    session_id=scenario.session_id,
                    member_id=member_id,
                    actor=actor,
                    now=dt.datetime.now(dt.UTC),
                )
                return booking.status.value

            return await _in_own_transaction(engine, work)

        results = await asyncio.gather(*(book(m) for m in scenario.members))

        assert results.count("booked") == 1
        assert results.count("waitlisted") == 19
        assert await _booked_count(db, scenario.session_id) == 1

    async def test_capacity_is_never_exceeded_under_load(
        self, db: AsyncSession, engine: AsyncEngine
    ) -> None:
        """Thirty racing for five seats."""
        scenario = await _scenario(db, capacity=5, members=30)
        settings = get_settings()

        async def book(member_id: uuid.UUID) -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str:
                booking = await BookingService(session_db, settings).create(
                    session_id=scenario.session_id,
                    member_id=member_id,
                    actor=actor,
                    now=dt.datetime.now(dt.UTC),
                )
                return booking.status.value

            return await _in_own_transaction(engine, work)

        results = await asyncio.gather(*(book(m) for m in scenario.members))

        assert results.count("booked") == 5
        assert results.count("waitlisted") == 25
        assert await _booked_count(db, scenario.session_id) == 5


@pytest.mark.concurrency
class TestConcurrentCancellations:
    async def test_two_cancellations_promote_two_different_members(
        self, db: AsyncSession, engine: AsyncEngine
    ) -> None:
        """The subtle race, and the one the brief describes as a real failure: "A
        spot opens up when someone cancels, but nobody thinks to check the binder
        for who was waiting."

        Two seats freed at the same instant must promote two *different* waitlisted
        members. Without the lock both cancellations read the same "earliest
        waitlisted" row, promote the same person, and leave a seat empty with
        someone still waiting for it.
        """
        scenario = await _scenario(db, capacity=2, members=5)
        settings = get_settings()

        booked: list[uuid.UUID] = []
        for member_id in scenario.members:
            booking = await BookingService(db, settings).create(
                session_id=scenario.session_id,
                member_id=member_id,
                actor=await db.get(User, scenario.actor_id),  # type: ignore[arg-type]
                now=dt.datetime.now(dt.UTC),
            )
            if booking.status is BookingStatus.BOOKED:
                booked.append(booking.id)
        await db.commit()
        assert len(booked) == 2

        async def cancel(booking_id: uuid.UUID) -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str | None:
                _, promoted = await BookingService(session_db, settings).cancel(
                    booking_id, actor=actor, now=dt.datetime.now(dt.UTC)
                )
                return str(promoted.id) if promoted else None

            return await _in_own_transaction(engine, work)

        promoted = await asyncio.gather(*(cancel(b) for b in booked))

        assert all(p is not None for p in promoted), promoted
        assert len(set(promoted)) == 2, "the same member was promoted twice"
        assert await _booked_count(db, scenario.session_id) == 2

    async def test_a_booking_and_a_cancellation_interleaved(
        self, db: AsyncSession, engine: AsyncEngine
    ) -> None:
        """A seat freeing while someone else is trying to take it.

        Whichever order they resolve in, the Booked count must equal capacity —
        never more, and never a seat left empty with a waitlist behind it.
        """
        scenario = await _scenario(db, capacity=1, members=3)
        settings = get_settings()

        holder = await BookingService(db, settings).create(
            session_id=scenario.session_id,
            member_id=scenario.members[0],
            actor=await db.get(User, scenario.actor_id),  # type: ignore[arg-type]
            now=dt.datetime.now(dt.UTC),
        )
        await BookingService(db, settings).create(
            session_id=scenario.session_id,
            member_id=scenario.members[1],
            actor=await db.get(User, scenario.actor_id),  # type: ignore[arg-type]
            now=dt.datetime.now(dt.UTC),
        )
        await db.commit()

        async def cancel() -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str:
                await BookingService(session_db, settings).cancel(
                    holder.id, actor=actor, now=dt.datetime.now(dt.UTC)
                )
                return "cancelled"

            return await _in_own_transaction(engine, work)

        async def book_third() -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str:
                booking = await BookingService(session_db, settings).create(
                    session_id=scenario.session_id,
                    member_id=scenario.members[2],
                    actor=actor,
                    now=dt.datetime.now(dt.UTC),
                )
                return booking.status.value

            return await _in_own_transaction(engine, work)

        await asyncio.gather(cancel(), book_third())

        assert await _booked_count(db, scenario.session_id) == 1
        counts = await _statuses(db, scenario.session_id)
        assert counts.get("cancelled") == 1


@pytest.mark.concurrency
class TestConcurrentSettlement:
    async def test_two_settlements_of_one_booking(
        self, db: AsyncSession, engine: AsyncEngine
    ) -> None:
        """One wins; the other gets the state-machine rejection rather than
        silently overwriting it. Without the row lock, last write wins and the
        timeline shows two contradictory outcomes."""
        scenario = await _scenario(db, capacity=5, members=1)
        settings = get_settings()

        booking = await BookingService(db, settings).create(
            session_id=scenario.session_id,
            member_id=scenario.members[0],
            actor=await db.get(User, scenario.actor_id),  # type: ignore[arg-type]
            now=dt.datetime.now(dt.UTC),
        )
        await db.execute(
            text("UPDATE sessions SET starts_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": scenario.session_id},
        )
        await db.commit()

        async def settle(attended: bool) -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str:
                result = await BookingService(session_db, settings).settle(
                    booking.id,
                    attended=attended,
                    actor=actor,
                    now=dt.datetime.now(dt.UTC),
                )
                return result.status.value

            return await _in_own_transaction(engine, work)

        results = await asyncio.gather(settle(True), settle(False))

        successes = [r for r in results if isinstance(r, str)]
        rejections = [r for r in results if isinstance(r, IllegalTransition)]
        assert len(successes) == 1
        assert len(rejections) == 1


@pytest.mark.concurrency
class TestDuplicateGuard:
    async def test_the_same_member_booked_twice_at_once(
        self, db: AsyncSession, engine: AsyncEngine
    ) -> None:
        """A double-submitted form, or two staff acting on the same phone call.

        The in-transaction check catches most of these; the partial unique index is
        the backstop that makes it impossible even when two transactions read
        before either writes. Either way the caller gets a clean 409, never a
        duplicate.
        """
        scenario = await _scenario(db, capacity=10, members=1)
        settings = get_settings()
        member_id = scenario.members[0]

        async def book() -> Any:
            async def work(session_db: AsyncSession, actor: User) -> str:
                booking = await BookingService(session_db, settings).create(
                    session_id=scenario.session_id,
                    member_id=member_id,
                    actor=actor,
                    now=dt.datetime.now(dt.UTC),
                )
                return booking.status.value

            try:
                return await _in_own_transaction(engine, work)
            except Exception as exc:  # the unique index, if the check was raced
                return exc

        results = await asyncio.gather(*(book() for _ in range(4)))

        created = [r for r in results if isinstance(r, str)]
        assert len(created) == 1, f"expected one booking, got {results}"

        active = (
            await db.execute(
                text(
                    "SELECT count(*) FROM bookings WHERE session_id = :s "
                    "AND member_id = :m AND status IN ('booked','waitlisted')"
                ),
                {"s": scenario.session_id, "m": member_id},
            )
        ).scalar_one()
        assert active == 1
