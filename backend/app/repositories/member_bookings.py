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
from typing import NamedTuple

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
    db: AsyncSession, *, member_id: uuid.UUID, limit: int = 100
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
