"""Turning member reads into the shapes a member is sent.

Split out of ``routers/me.py`` so that file reads as what it is — a list of
endpoints and the rules each one enforces — rather than interleaving those with
the mechanical business of mapping rows onto models.

Everything here converts to the **studio's** local time. That is not a display
nicety: a 07:00 class in Asia/Kolkata falls on the previous date in UTC, and a
member reading "yesterday" for a class they are walking into this morning would
be right to distrust the rest of the page.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound
from app.models.enums import BookingStatus
from app.repositories.member_bookings import BookableRow, MyBookingRow, my_bookings
from app.schemas.me import BookableSession, MyBooking


def render_booking(row: MyBookingRow, tz: dt.tzinfo, now: dt.datetime) -> MyBooking:
    """One row, in the studio's local time.

    Converted here rather than sent as an instant, for the same reason every other
    date-bucketed read does it: a 07:00 class in Asia/Kolkata is the previous day
    in UTC, and a member reading "yesterday" for a class they are going to this
    morning would be right to distrust everything else on the page.
    """
    local = row.session.starts_at.astimezone(tz)
    return MyBooking(
        id=row.booking.id,
        status=row.booking.status,
        booked_at=row.booking.booked_at,
        session_date=local.date(),
        start_time=local.time(),
        duration_min=row.session.duration_min,
        class_id=row.studio_class.id,
        class_title=row.studio_class.title,
        discipline=row.studio_class.discipline,
        instructor_name=row.instructor_name,
        room_name=row.room_name,
        session_has_passed=row.session.starts_at <= now,
        waitlist_position=row.waitlist_position,
        can_cancel=row.can_cancel(now),
    )



async def one_booking(
    db: AsyncSession,
    *,
    member_id: uuid.UUID,
    booking_id: uuid.UUID,
    settings: Settings,
    now: dt.datetime,
) -> MyBooking:
    """Re-read one booking as the member sees it, after writing it.

    A second query rather than assembling the response from the ORM object,
    because the row a member reads carries the class, instructor, room and queue
    position — all from the same joined read their list uses. What they see after
    booking is then exactly what they will see on the list.
    """
    rows = await my_bookings(db, member_id=member_id, booking_id=booking_id, limit=1)
    if not rows:
        raise NotFound("No such booking.")
    return render_booking(rows[0], settings.tz, now)



def render_bookable(
    row: BookableRow, counts: dict[BookingStatus, int], tz: dt.tzinfo
) -> BookableSession:
    """One upcoming class, with seats left rather than seats taken.

    ``spots_remaining`` counts everything that occupies a place — booked, attended
    and no-show — for the same reason the public timetable does: a member who did
    not turn up still had the mat.
    """
    local = row.session.starts_at.astimezone(tz)
    taken = (
        counts.get(BookingStatus.BOOKED, 0)
        + counts.get(BookingStatus.ATTENDED, 0)
        + counts.get(BookingStatus.NO_SHOW, 0)
    )
    remaining = max(row.session.capacity - taken, 0)
    return BookableSession(
        id=row.session.id,
        session_date=local.date(),
        start_time=local.time(),
        duration_min=row.session.duration_min,
        class_id=row.studio_class.id,
        class_title=row.studio_class.title,
        discipline=row.studio_class.discipline,
        description=row.studio_class.description,
        instructor_name=row.instructor_name,
        room_name=row.room_name,
        spots_remaining=remaining,
        is_full=remaining == 0,
        my_status=row.my_status,
        my_waitlist_position=row.my_waitlist_position,
    )
