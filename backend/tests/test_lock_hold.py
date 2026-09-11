"""How long the session lock is actually held.

``architecture.md`` claims the cancel-and-promote transaction is eight round trips
and that the lock is held for tens of milliseconds. Those are checkable claims, and
a document that makes them without a test is asserting rather than knowing — which
is the thing this project has been trying not to do.

Two assertions, and the first matters more:

* **The round-trip count is bounded.** Deterministic, so it cannot flake, and it is
  the thing that actually governs lock hold time. If somebody adds a query inside
  the locked section, this fails and names the number.
* **The wall-clock duration is recorded.** Environment-dependent, so the bound is
  deliberately generous — it exists to catch an order-of-magnitude regression, such
  as an HTTP call sneaking inside the lock, not to police milliseconds.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.db.engine import build_engine, build_session_factory
from app.models.enums import BookingStatus
from app.models.user import User
from app.services.booking_service import BookingService
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.usefixtures("migrated_schema")

# The statement count for cancel-and-promote as designed. Raising this is a real
# decision — every extra statement is time the session row stays locked and every
# other booking on it waits — so it is written down rather than inferred.
MAX_STATEMENTS_IN_LOCKED_SECTION = 12

# Generous by an order of magnitude. Against a local database the transaction is a
# few milliseconds; against a same-region managed database, tens. This bound is
# here to catch something structurally wrong, not to measure the machine.
MAX_LOCK_HOLD_MS = 1_000


class StatementCounter:
    """Counts statements issued on an engine, from the lock onward."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.counting = False

    def start(self) -> None:
        self.statements.clear()
        self.counting = True

    def stop(self) -> None:
        self.counting = False

    def record(self, sql: str) -> None:
        # Stored in full: assertions search for clauses like FOR UPDATE, which sit
        # at the end of a long SELECT and would be lost to truncation. Shortening
        # happens only when a failure message is built.
        if self.counting:
            self.statements.append(" ".join(sql.split()))

    def summary(self) -> str:
        """Shortened, for a failure message only."""
        return "\n  ".join(s[:100] for s in self.statements)


@pytest.fixture
def counter(engine: AsyncEngine) -> Iterator[StatementCounter]:
    tracker = StatementCounter()

    def before_cursor_execute(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        tracker.record(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    yield tracker
    event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = build_engine(url=TEST_DATABASE_URL)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = build_session_factory(engine)
    async with factory() as session:
        yield session
        await session.rollback()


async def _full_session_with_waitlist(
    db: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, User]:
    """A one-seat session with someone booked and someone waiting.

    That shape is the point: cancelling the booked place has to promote the waiting
    one, which is the longest path through the locked section.
    """
    tag = uuid.uuid4().hex[:8]
    ids = {k: uuid.uuid4() for k in ("room", "user", "cls", "session", "m1", "m2")}

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
            "default_capacity) VALUES (:id, :t, 'yoga', 60, 1)"
        ),
        {"id": ids["cls"], "t": f"Class {tag}"},
    )
    await db.execute(
        text(
            "INSERT INTO sessions (id, class_id, starts_at, primary_instructor_id, "
            "room_id, duration_min, capacity) "
            "VALUES (:id, :c, :s, :u, :r, 60, 1)"
        ),
        {
            "id": ids["session"],
            "c": ids["cls"],
            "s": dt.datetime(2028, 4, 5, 18, 0, tzinfo=dt.UTC),
            "u": ids["user"],
            "r": ids["room"],
        },
    )
    for key, name in (("m1", "Holder"), ("m2", "Waiting")):
        await db.execute(
            text(
                "INSERT INTO members (id, full_name, email, membership_expiry) "
                "VALUES (:id, :n, :e, '2030-01-01')"
            ),
            {"id": ids[key], "n": name, "e": f"{name.lower()}-{tag}@example.com"},
        )
    await db.commit()

    actor = await db.get(User, ids["user"])
    assert actor is not None

    service = BookingService(db, get_settings())
    now = dt.datetime.now(dt.UTC)
    holder = await service.create(
        session_id=ids["session"], member_id=ids["m1"], actor=actor, now=now
    )
    waiting = await service.create(
        session_id=ids["session"], member_id=ids["m2"], actor=actor, now=now
    )
    await db.commit()

    assert holder.status is BookingStatus.BOOKED
    assert waiting.status is BookingStatus.WAITLISTED
    return holder.id, ids["session"], actor


class TestLockHold:
    async def test_the_locked_section_issues_a_bounded_number_of_statements(
        self, db: AsyncSession, counter: StatementCounter
    ) -> None:
        """The claim in architecture.md, made checkable.

        Every statement between taking the lock and committing is time that other
        bookings on the same session spend waiting, so the count is the thing worth
        constraining — and unlike a duration it cannot flake.
        """
        booking_id, _, actor = await _full_session_with_waitlist(db)
        service = BookingService(db, get_settings())

        counter.start()
        await service.cancel(booking_id, actor=actor, now=dt.datetime.now(dt.UTC))
        await db.commit()
        counter.stop()

        assert len(counter.statements) <= MAX_STATEMENTS_IN_LOCKED_SECTION, (
            f"cancel-and-promote issued {len(counter.statements)} statements while "
            f"holding the session lock:\n  " + "\n  ".join(counter.statements)
        )

    async def test_the_lock_is_taken_and_the_promotion_is_in_the_same_transaction(
        self, db: AsyncSession, counter: StatementCounter
    ) -> None:
        """FOR UPDATE, then the promotion, then one COMMIT.

        A promotion that landed in a *second* transaction would leave a window in
        which the seat is free and the waitlist has not been consulted — which is
        the failure the brief opens with.
        """
        booking_id, _, actor = await _full_session_with_waitlist(db)
        service = BookingService(db, get_settings())

        counter.start()
        _, promoted = await service.cancel(booking_id, actor=actor, now=dt.datetime.now(dt.UTC))
        statements_before_commit = list(counter.statements)
        await db.commit()
        counter.stop()

        assert promoted is not None, "cancelling a booked place must promote"

        joined = " ".join(statements_before_commit).upper()
        assert "FOR UPDATE" in joined, "the session row was never locked"
        # The promotion's UPDATE has to be inside the same transaction as the
        # cancellation, so it must appear before the commit.
        assert sum("UPDATE BOOKINGS" in s.upper() for s in statements_before_commit) >= 2

    async def test_the_lock_hold_duration_is_recorded(
        self, db: AsyncSession, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Measured rather than asserted, with a deliberately loose bound.

        The bound is an order of magnitude clear of reality, so this catches
        something structurally wrong — an HTTP call or a sleep inside the locked
        section — rather than policing the speed of the machine it runs on.
        """
        booking_id, _, actor = await _full_session_with_waitlist(db)
        service = BookingService(db, get_settings())

        started = time.perf_counter()
        await service.cancel(booking_id, actor=actor, now=dt.datetime.now(dt.UTC))
        await db.commit()
        elapsed_ms = (time.perf_counter() - started) * 1000

        with capsys.disabled():
            print(f"\n  lock held for {elapsed_ms:.1f} ms (bound {MAX_LOCK_HOLD_MS} ms)")

        assert elapsed_ms < MAX_LOCK_HOLD_MS
