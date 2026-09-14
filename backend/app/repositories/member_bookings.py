"""The one read a member makes about themselves.

A separate query rather than a branch inside ``search_bookings``, and the reason
is the scoping. Goal 6's search is filtered by ``visible_sessions_clause``, which
answers "which sessions may this user see" — and for a member that is deliberately
``false()``, because those endpoints return staff shapes. Teaching that clause to
mean something else for one role would make every other caller of it subtly
role-dependent.

The rule here is simpler and belongs in one place: **a member's bookings are the
rows whose ``member_id`` is theirs.** Not "bookings on sessions they can see" —
there is no such set — just their own rows, resolved from their credential by
``get_current_member`` and never from the request.

What it *does* reuse is ``waitlist_position_column``. That ordering has to match
the promotion query's exactly, and a second copy would be a second thing to get
wrong — the number the member reads and the seat they actually get would drift
apart silently.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.class_session import ClassSession
from app.models.enums import BookingStatus
from app.models.room import Room
from app.models.studio_class import StudioClass
from app.models.user import User
from app.repositories.booking_search import waitlist_position_column

# Terminal statuses cannot be cancelled again; a settled register is history.
_CANCELLABLE = (BookingStatus.BOOKED, BookingStatus.WAITLISTED)


class MyBookingRow(NamedTuple):
    booking: Booking
    session: ClassSession
    studio_class: StudioClass
    instructor_name: str
    room_name: str
    waitlist_position: int | None

    def can_cancel(self, now: dt.datetime) -> bool:
        """Whether this member may still call it off.

        The same two conditions the service enforces — an active booking, on a
        session that has not started. Computed here so the interface is told the
        answer rather than deriving it, because a button that appears when the API
        would refuse is worse than no button at all.

        It is a display hint and nothing more. ``BookingService.cancel`` re-checks
        both under the session's row lock, which is where the decision actually
        happens; this is a copy that is allowed to be stale for a second.
        """
        return self.booking.status in _CANCELLABLE and self.session.starts_at > now


async def my_bookings(
    db: AsyncSession,
    *,
    member_id: uuid.UUID,
    limit: int = 100,
    booking_id: uuid.UUID | None = None,
) -> list[MyBookingRow]:
    """This member's bookings, soonest session first.

    Ordered by the session rather than by when it was booked: a member opening
    this list is asking "what am I going in for", and the answer is a timetable.
    Past sessions follow, most recent first, so the same list doubles as their
    history without a second request.

    Cancelled bookings are included. A member who cancelled and wants to know they
    did is asking a reasonable question, and the row says so; hiding it would make
    a place that was given up look like one that never existed.

    Soft-deleted sessions are excluded, matching every other read: a deleted
    session's bookings are cancelled with it and there is nothing to attend.
    """
    query = (
        select(
            Booking,
            ClassSession,
            StudioClass,
            User.full_name,
            Room.name,
            waitlist_position_column(),
        )
        .join(ClassSession, ClassSession.id == Booking.session_id)
        .join(StudioClass, StudioClass.id == ClassSession.class_id)
        .join(User, User.id == ClassSession.primary_instructor_id)
        .join(Room, Room.id == ClassSession.room_id)
        .where(
            Booking.member_id == member_id,
            ClassSession.deleted_at.is_(None),
        )
        .order_by(ClassSession.starts_at.desc())
        .limit(limit)
    )
    # `booking_id` narrows to one row *in addition to* the member filter, never
    # instead of it. An endpoint that looked a booking up by id alone would hand
    # any member anybody's booking, which is the whole class of bug this module
    # exists to make impossible.
    if booking_id is not None:
        query = query.where(Booking.id == booking_id)

    return [
        MyBookingRow(
            booking=row[0],
            session=row[1],
            studio_class=row[2],
            instructor_name=row[3],
            room_name=row[4],
            waitlist_position=row[5],
        )
        for row in (await db.execute(query)).all()
    ]


class BookableRow(NamedTuple):
    session: ClassSession
    studio_class: StudioClass
    instructor_name: str
    room_name: str
    my_status: BookingStatus | None
    my_waitlist_position: int | None


async def bookable_sessions(
    db: AsyncSession,
    *,
    member_id: uuid.UUID,
    now: dt.datetime,
    until: dt.datetime,
    limit: int,
) -> list[BookableRow]:
    """Upcoming sessions a member could book, with their own status on each.

    Forward only, from **now** rather than from midnight: a timetable still
    offering this morning's class at four in the afternoon is worse than a short
    one. Archived classes and soft-deleted sessions are excluded, because the
    booking service would refuse them anyway and an option that cannot be taken is
    not an option.

    The member's own status arrives as a correlated subquery rather than an outer
    join, so a member with no bookings pays nothing and the row count cannot be
    multiplied by a join that matches twice. Only *active* bookings count: a
    cancelled place is not a reason to stop somebody rebooking, and the question
    this column answers is "may I book this".
    """
    def own(column: Any) -> Any:
        """One column of this member's own active booking on the session in hand.

        Two correlated subqueries rather than an outer join to `bookings`: a join
        would multiply the row when a member has a cancelled booking on the same
        session as well as an active one, which is a real case — cancelling and
        rebooking is ordinary. Restricting to active statuses makes at most one
        row match, and a scalar subquery says that in the type rather than relying
        on it.
        """
        return (
            select(column)
            .where(
                Booking.session_id == ClassSession.id,
                Booking.member_id == member_id,
                Booking.status.in_(_CANCELLABLE),
            )
            .limit(1)
            .correlate(ClassSession)
            .scalar_subquery()
        )

    mine = own(Booking.status)
    # The same column function the desk's list and the promotion query use, so the
    # number on the timetable, the number on the member's own list and the seat
    # they actually get are all counted one way.
    my_place = own(waitlist_position_column())

    query = (
        select(ClassSession, StudioClass, User.full_name, Room.name, mine, my_place)
        .join(StudioClass, StudioClass.id == ClassSession.class_id)
        .join(User, User.id == ClassSession.primary_instructor_id)
        .join(Room, Room.id == ClassSession.room_id)
        .where(
            ClassSession.deleted_at.is_(None),
            StudioClass.archived_at.is_(None),
            ClassSession.starts_at >= now,
            ClassSession.starts_at < until,
        )
        .order_by(ClassSession.starts_at)
        .limit(limit)
    )

    return [
        BookableRow(
            session=row[0],
            studio_class=row[1],
            instructor_name=row[2],
            room_name=row[3],
            my_status=row[4],
            my_waitlist_position=row[5],
        )
        for row in (await db.execute(query)).all()
    ]
