"""The bookings list query (goal 6).

Goal 6 is the most heavily specified read in the brief — text search over member
name and email, filters for class, session and status, three sort options,
pagination, and the total number of matches — with the explicit instruction not to
"load every booking into the browser and filter there".

So it is one statement. Everything the list needs is joined once, the total comes
back on the same rows as a window function, and the page is cut in the database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import Select, Text, case, or_, select, tuple_
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc
from app.models.booking import Booking
from app.models.class_session import ClassSession
from app.models.enums import BookingStatus
from app.models.member import Member
from app.models.studio_class import StudioClass
from app.models.user import User
from app.repositories.visibility import visible_sessions_clause
from app.schemas.booking_search import BookingSort, SortDirection

# Long search terms share few trigrams with anything, so the index stops helping
# and the query degrades to a sequential scan. Capped at the API boundary too.
MAX_SEARCH_LENGTH = 100


class BookingRow(NamedTuple):
    """One joined row, before it becomes a response model."""

    booking: Booking
    member: Member
    session: ClassSession
    studio_class: StudioClass
    # 1-based place in this session's queue, or None when the booking is not
    # waitlisted. See ``waitlist_position_column``.
    waitlist_position: int | None


class BookingSearchResult(NamedTuple):
    rows: list[BookingRow]
    total: int


def waitlist_position_column() -> Any:
    """How far down the queue a waitlisted booking is, as SQL.

    The number a member is told when they ring up, so it has to be **the same
    ordering the promotion actually uses** — ``booked_at`` then ``id``. Getting
    that wrong would not fail; it would just make the studio tell somebody they
    are third when they are fourth, which nobody discovers until a seat frees and
    the wrong person gets it.

    Counting earlier rows rather than a window function, because a window over the
    result set would rank within *the page*: the bookings list is paginated across
    many sessions, so the rows in front of this one are usually not in it. The
    correlated count asks the whole table.

    The row-value comparison ``(booked_at, id) < (booked_at, id)`` is the same
    tiebreak the promotion query applies, written once so the two cannot drift.

    Wrapped in ``CASE`` so it is only evaluated for waitlisted rows — a page of
    fifty settled bookings should not run fifty subqueries to answer a question
    none of them are asking. ``ix_bookings_session_status`` covers the count.
    """
    earlier = Booking.__table__.alias("earlier")
    ahead = (
        select(sa_func.count())
        .select_from(earlier)
        .where(
            earlier.c.session_id == Booking.session_id,
            earlier.c.status == BookingStatus.WAITLISTED,
            tuple_(earlier.c.booked_at, earlier.c.id)
            < tuple_(Booking.booked_at, Booking.id),
        )
        .scalar_subquery()
    )
    return case(
        (Booking.status == BookingStatus.WAITLISTED, ahead + 1),
        else_=None,
    ).label("waitlist_position")


def _apply_filters(
    query: Select[Any],
    *,
    viewer: User,
    tz: ZoneInfo,
    search: str | None,
    class_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    status: BookingStatus | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
) -> Select[Any]:
    """Compose every filter, including the one that is not optional.

    ``visible_sessions_clause`` is applied here rather than left to the caller:
    goal 6 says the list covers "every session the viewer can see", and a scoping
    rule that has to be remembered at each call site is a rule that will eventually
    be forgotten at one of them.
    """
    query = query.where(
        ClassSession.deleted_at.is_(None),
        visible_sessions_clause(viewer),
    )

    if status is not None:
        query = query.where(Booking.status == status)
    if session_id is not None:
        query = query.where(Booking.session_id == session_id)
    if class_id is not None:
        query = query.where(ClassSession.class_id == class_id)

    # The range is over the *class dates*, not over when the bookings were taken.
    # That is the question somebody at a desk is actually asking — "what is on
    # next week, and who is coming" — and it is the same thing `date_from` and
    # `date_to` mean on the sessions endpoint, so one word does not mean two
    # things in one API.
    #
    # Compared as instants against the studio's timezone rather than by casting
    # `starts_at` to a date: a cast would be computed per row and could not use
    # the index on `starts_at`, and it would also bucket by UTC days, which puts
    # a 7am class in Kolkata on the previous day.
    if date_from is not None:
        query = query.where(ClassSession.starts_at >= to_utc(date_from, dt.time.min, tz))
    if date_to is not None:
        # The whole of the end day, which is what a date range means to anybody
        # filling in a form.
        query = query.where(
            ClassSession.starts_at < to_utc(date_to + dt.timedelta(days=1), dt.time.min, tz)
        )

    if search:
        pattern = f"%{search.strip()[:MAX_SEARCH_LENGTH]}%"
        # Member.email is citext, and the planner will not use a trigram index for
        # a citext-native operator — it sequentially scans instead, with identical
        # results. The cast here has to match the cast the index was built on.
        query = query.where(
            or_(
                Member.full_name.ilike(pattern),
                Member.email.cast(Text).ilike(pattern),
            )
        )

    return query


def _order_by(query: Select[Any], sort: BookingSort, direction: SortDirection) -> Select[Any]:
    """Apply the ordering, always with a stable tiebreak.

    Without ``Booking.id`` last, two rows with the same sort key can swap places
    between requests — and a row then gets shown twice or skipped entirely as the
    client pages through. Silent, and only visible as "a booking went missing".
    """
    columns = {
        BookingSort.BOOKED_AT: Booking.booked_at,
        BookingSort.STATUS: Booking.status,
        BookingSort.SESSION: ClassSession.starts_at,
    }
    column = columns[sort]
    ordered = column.desc() if direction is SortDirection.DESC else column.asc()
    return query.order_by(ordered, Booking.id)


async def search_bookings(
    db: AsyncSession,
    *,
    viewer: User,
    tz: ZoneInfo,
    search: str | None = None,
    class_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    status: BookingStatus | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    sort: BookingSort = BookingSort.BOOKED_AT,
    direction: SortDirection = SortDirection.DESC,
    limit: int = 50,
    offset: int = 0,
) -> BookingSearchResult:
    """Run the list query.

    The total comes from ``count(*) OVER ()`` in the same statement rather than a
    second ``COUNT`` query. Two reasons, and the second matters more: it is one
    round trip instead of two, and the count and the rows come from the same
    snapshot — so the total can never disagree with the page beside it. The cost is
    that Postgres materialises the full filtered set to compute the window, which
    is the first thing that breaks at 100x and is recorded as such in schema.md.
    """
    total_column = sa_func.count().over().label("total_matches")

    query = (
        select(
            Booking,
            Member,
            ClassSession,
            StudioClass,
            total_column,
            waitlist_position_column(),
        )
        .join(Member, Member.id == Booking.member_id)
        .join(ClassSession, ClassSession.id == Booking.session_id)
        .join(StudioClass, StudioClass.id == ClassSession.class_id)
    )
    query = _apply_filters(
        query,
        viewer=viewer,
        tz=tz,
        search=search,
        class_id=class_id,
        session_id=session_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    query = _order_by(query, sort, direction).limit(limit).offset(offset)

    result = (await db.execute(query)).all()

    if not result:
        # No rows means no window to count over, so the total is not in the
        # result — it is zero by construction.
        return BookingSearchResult(rows=[], total=0)

    return BookingSearchResult(
        rows=[
            BookingRow(
                booking=row[0],
                member=row[1],
                session=row[2],
                studio_class=row[3],
                waitlist_position=row[5],
            )
            for row in result
        ],
        total=int(result[0][4]),
    )


def has_passed(session: ClassSession, now: dt.datetime) -> bool:
    return session.starts_at <= now
