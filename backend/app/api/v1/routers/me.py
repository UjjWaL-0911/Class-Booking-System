"""What a signed-in member can see about themselves.

Every endpoint here takes ``CurrentMember``, which resolves the member record from
the credential. **None of them accept a member id**, and that is the whole security
model of self-service: the person being read is derived from who is asking, so
there is no parameter to tamper with and no scoping check to forget.

That matters more than it looks. ``BookingService`` and the queries behind it have
no row-level authorization of their own — they trust the caller to have decided
whose rows these are. Under the staff endpoints that decision is the ``StaffUser``
guard; here it is the credential itself.

The shapes are in ``schemas/me.py`` and are written from scratch rather than
filtered from the staff models, for the reason ``PublicSession`` exists.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

from app.core.deps import Config, CurrentMember, DbSession, Now
from app.core.time import today as studio_today
from app.repositories.member_bookings import MyBookingRow, my_bookings
from app.schemas.me import MyBooking, MyMembership

router = APIRouter(prefix="/me", tags=["me"])

# One member cannot hold more than a term's worth of places, and an unbounded
# read is an unbounded read even when it is somebody's own.
MAX_BOOKINGS = 200


@router.get("/membership", response_model=MyMembership, summary="My membership")
async def my_membership(
    member: CurrentMember, settings: Config, now: Now
) -> MyMembership:
    """Who I am and whether I may book today.

    ``is_expired`` is decided here, in the studio's timezone, rather than left to
    the browser to work out from a date — a membership is valid *through* its
    expiry, and the browser's idea of today is whatever timezone the phone is in.
    """
    today = studio_today(settings.tz, now)
    return MyMembership(
        full_name=member.full_name,
        email=member.email,
        membership_expiry=member.membership_expiry,
        is_expired=member.membership_expiry < today,
    )


@router.get("/bookings", response_model=list[MyBooking], summary="My bookings")
async def my_bookings_list(
    db: DbSession, member: CurrentMember, settings: Config, now: Now
) -> list[MyBooking]:
    """Everything this member has booked, soonest first, history after.

    Unpaginated, deliberately: this is one person's own list, bounded by how many
    classes they attend rather than by how big the studio is. The cap exists so
    that "bounded in practice" is also bounded in the query.
    """
    rows = await my_bookings(db, member_id=member.id, limit=MAX_BOOKINGS)
    return [_render(row, settings.tz, now) for row in rows]


def _render(row: MyBookingRow, tz: dt.tzinfo, now: dt.datetime) -> MyBooking:
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
        class_title=row.studio_class.title,
        discipline=row.studio_class.discipline,
        instructor_name=row.instructor_name,
        room_name=row.room_name,
        session_has_passed=row.session.starts_at <= now,
        waitlist_position=row.waitlist_position,
        can_cancel=row.can_cancel(now),
    )
