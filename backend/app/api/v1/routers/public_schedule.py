"""The one endpoint anybody on the internet can reach (beyond health and sign-in).

Not one of the ten goals. It exists because every other screen in this system is
behind a login, so the product is invisible to somebody who has not been given an
account — and a studio's timetable is the least private thing it owns. It is
recorded as a deliberate addition in ``decisions.md``.

**Everything unusual about this file follows from it being public.**

*It has its own response model.* ``PublicSession`` is written from scratch rather
than derived from ``SessionOut``, so no field can reach an anonymous caller by being
added to a shape that is also served to staff. See ``schemas/public_schedule.py``.

*It reads forward only, and not far.* A fixed two-week window, capped. There is no
`date_from`, no offset and no page size for a caller to widen: an endpoint with no
credentials should not also have a way to ask for everything.

*It excludes archived classes and deleted sessions.* Archiving means "not offered",
and the public schedule is the one place where that word means exactly what it says.

*It says how much room is left, not how many are booked.* A remaining count is what a
prospective member needs; the booked count is an operational figure, and publishing
it tells the internet how the studio's business is doing.

*Nothing here is cached at the edge yet.* The response is small and the query is one
statement against an indexed column, but this is the only endpoint whose traffic is
not bounded by the number of staff accounts, so a `Cache-Control` header is the first
thing to add if it ever matters.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import Config, DbSession, Now
from app.core.time import to_utc
from app.core.time import today as studio_today
from app.models.class_session import ClassSession
from app.models.enums import BookingStatus
from app.models.studio_class import StudioClass
from app.schemas.public_schedule import PublicSchedule, PublicSession
from app.services.session_service import SessionService

router = APIRouter(prefix="/public", tags=["public"])

# Two weeks is what a studio puts on a poster. The cap is not a page size — it is
# the ceiling on what one unauthenticated request can cost.
DEFAULT_DAYS_AHEAD = 14
MAX_DAYS_AHEAD = 31
MAX_SESSIONS = 200


@router.get(
    "/schedule",
    response_model=PublicSchedule,
    summary="Upcoming classes, for anyone",
)
async def public_schedule(
    db: DbSession,
    settings: Config,
    now: Now,
    days: int = Query(default=DEFAULT_DAYS_AHEAD, ge=1, le=MAX_DAYS_AHEAD),
) -> PublicSchedule:
    """Upcoming classes in the studio's timezone. No authentication.

    The window starts at **now**, not at midnight: a schedule that still advertises
    this morning's class at four in the afternoon is worse than one that is simply
    short.
    """
    today = studio_today(settings.tz, now)
    ends = today + dt.timedelta(days=days)

    query = (
        select(ClassSession)
        .join(StudioClass, StudioClass.id == ClassSession.class_id)
        .where(
            ClassSession.deleted_at.is_(None),
            StudioClass.archived_at.is_(None),
            ClassSession.starts_at >= now,
            ClassSession.starts_at < to_utc(ends, dt.time.min, settings.tz),
        )
        .options(
            selectinload(ClassSession.studio_class),
            selectinload(ClassSession.room),
            selectinload(ClassSession.primary_instructor),
        )
        .order_by(ClassSession.starts_at)
    )
    # One more than the cap, so hitting it is detectable rather than assumed.
    sessions = list((await db.execute(query.limit(MAX_SESSIONS + 1))).scalars().all())
    truncated = len(sessions) > MAX_SESSIONS
    sessions = sessions[:MAX_SESSIONS]

    # One grouped query for every session on the page rather than one per session —
    # the same helper the timetable uses, for the same reason.
    counts = await SessionService(db, settings).counts_for([s.id for s in sessions])

    return PublicSchedule(
        days_ahead=days,
        starts=today,
        ends=ends,
        truncated=truncated,
        sessions=[_to_public(s, counts[s.id], settings.tz) for s in sessions],
    )


def _to_public(
    session: ClassSession,
    counts: dict[BookingStatus, int],
    tz: dt.tzinfo,
) -> PublicSession:
    """Shape one session for a stranger.

    ``spots_remaining`` counts *active* bookings only. A session in this window has
    not happened yet, so nothing on it is settled — but writing the subtraction
    against `booked` alone would be a quiet assumption that this endpoint never
    looks backwards, and somebody widening the window later would not notice it
    breaking. Counting what occupies a seat is the same rule the interface uses.
    """
    local = session.starts_at.astimezone(tz)
    taken = (
        counts.get(BookingStatus.BOOKED, 0)
        + counts.get(BookingStatus.ATTENDED, 0)
        + counts.get(BookingStatus.NO_SHOW, 0)
    )
    remaining = max(session.capacity - taken, 0)

    return PublicSession(
        session_date=local.date(),
        start_time=local.time(),
        duration_min=session.duration_min,
        class_title=session.studio_class.title,
        discipline=session.studio_class.discipline,
        description=session.studio_class.description,
        instructor_name=session.primary_instructor.full_name,
        room_name=session.room.name,
        spots_remaining=remaining,
        is_full=remaining == 0,
    )
