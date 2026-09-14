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
import uuid

from fastapi import APIRouter, Query, status

from app.api.v1.routers.me_rendering import one_booking, render_bookable, render_booking
from app.core.deps import Config, CurrentMember, CurrentUser, DbSession, Now
from app.core.errors import NotFound, RuleViolation
from app.core.time import to_utc
from app.core.time import today as studio_today
from app.repositories.member_bookings import (
    bookable_sessions,
    my_bookings,
)
from app.schemas.me import (
    BookableSession,
    MyBooking,
    MyBookingCreate,
    MyCancellation,
    MyMembership,
)
from app.services.booking_service import BookingService
from app.services.session_service import SessionService

router = APIRouter(prefix="/me", tags=["me"])

# One member cannot hold more than a term's worth of places, and an unbounded
# read is an unbounded read even when it is somebody's own.
MAX_BOOKINGS = 200

# What a member can see ahead, matching the public timetable's default. An
# unauthenticated caller and a signed-in member are asking the same question about
# the same studio; only the ids and their own status differ.
DEFAULT_DAYS_AHEAD = 14
MAX_DAYS_AHEAD = 31
MAX_SESSIONS = 200


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
    return [render_booking(row, settings.tz, now) for row in rows]


@router.get("/schedule", response_model=list[BookableSession], summary="Classes I could book")
async def my_schedule(
    db: DbSession,
    member: CurrentMember,
    settings: Config,
    now: Now,
    days: int = Query(default=DEFAULT_DAYS_AHEAD, ge=1, le=MAX_DAYS_AHEAD),
) -> list[BookableSession]:
    """Upcoming classes, each carrying whether this member already has a place.

    A member-facing twin of ``/public/schedule`` rather than an extension of it.
    The public one deliberately exposes no session id, because a stranger has
    nothing to do with one; a member does, since naming a session is how they book
    it. Two audiences, two shapes, neither filtered from the other.

    Seat counts come from the same grouped helper the timetable uses — one query
    for the whole page rather than one per session.
    """
    ends = to_utc(
        studio_today(settings.tz, now) + dt.timedelta(days=days), dt.time.min, settings.tz
    )
    rows = await bookable_sessions(
        db, member_id=member.id, now=now, until=ends, limit=MAX_SESSIONS
    )
    counts = await SessionService(db, settings).counts_for([row.session.id for row in rows])
    return [render_bookable(row, counts[row.session.id], settings.tz) for row in rows]


@router.post(
    "/bookings",
    response_model=MyBooking,
    status_code=status.HTTP_201_CREATED,
    summary="Book myself onto a class",
)
async def book_myself(
    payload: MyBookingCreate,
    db: DbSession,
    member: CurrentMember,
    user: CurrentUser,
    settings: Config,
    now: Now,
) -> MyBooking:
    """Take a place, or join the waiting list if the class is full.

    **The same method the desk calls**, with the same lock, the same capacity
    decision, the same expiry check and the same audit event. Every rule that
    applies when staff book on somebody's behalf applies here because it is
    literally the same code — a second booking path would eventually disagree with
    the first, and the disagreement would be invisible until two members compared
    their histories.

    Nothing is added for members and nothing is relaxed. A full class waitlists
    them, an archived class refuses, a started session refuses, and a lapsed
    membership refuses naming the date it lapsed — the last being why switching on
    a login never had to know anything about payment.

    The member id comes from ``CurrentMember``; the actor is that member's own
    account. So the timeline records that this person booked *themselves*, which is
    a different fact from the desk booking for them, and goal 9's history tells the
    two apart for free.
    """
    booking = await BookingService(db, settings).create(
        session_id=payload.session_id,
        member_id=member.id,
        actor=user,
        now=now,
        note=payload.note,
    )
    await db.commit()
    return await one_booking(
        db, member_id=member.id, booking_id=booking.id, settings=settings, now=now
    )


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=MyBooking,
    summary="Cancel my own booking",
)
async def cancel_my_booking(
    booking_id: uuid.UUID,
    payload: MyCancellation,
    db: DbSession,
    member: CurrentMember,
    user: CurrentUser,
    settings: Config,
    now: Now,
) -> MyBooking:
    """Give up my place. Whoever is first on the waiting list takes it.

    **Ownership is checked here, because the service does not check it.**
    ``BookingService.cancel`` takes a booking id and trusts its caller to have
    decided whose it is — under the staff endpoint that decision is the
    ``StaffUser`` guard, and staff may cancel anybody's. So this endpoint looks the
    booking up *within this member's own rows* and 404s otherwise. Not 403, which
    would confirm the booking exists and let somebody enumerate ids one at a time.

    **One rule is stricter here than for staff**, deliberately rather than by
    drift: a member cannot cancel a class that has already started. Staff can,
    because staff are correcting a record — somebody rang, they are not coming. A
    member cancelling is making a decision about attendance, and that decision is
    meaningless once the class is running: the seat it frees can no longer be used,
    and it muddies the register the instructor is about to mark. It also keeps the
    server's answer and ``can_cancel`` on the member's own list saying the same
    thing, which is the difference between a disabled button and a broken one.

    The promotion is the ordinary one, in this same transaction — there is no code
    path where a seat frees and the waitlist is not considered.
    """
    existing = await my_bookings(db, member_id=member.id, booking_id=booking_id, limit=1)
    if not existing:
        raise NotFound("No such booking.")
    if existing[0].session.starts_at <= now:
        raise RuleViolation("This class has already started.")

    await BookingService(db, settings).cancel(booking_id, actor=user, now=now, note=payload.note)
    await db.commit()
    return await one_booking(
        db, member_id=member.id, booking_id=booking_id, settings=settings, now=now
    )
