"""Booking endpoints (goal 4) and the immutable timeline (goal 9).

Who may do what, which is the interpretation of goals 1 and 4 this system
implements:

* **Create and cancel** — staff only, on any session. Goal 1 bars instructors from
  creating bookings, and goal 4 assigns create/cancel/settle to staff.
* **Settle and note** — staff on any session; an instructor on their own sessions
  only. The scenario asks instructors to "record who actually showed up", so
  settlement is theirs; the row-level check happens inside the transaction, after
  the session row is locked.
* **Timeline** — readable by anyone who can see the session. Append-only, with no
  edit or delete endpoint at any level, because there is no such operation to
  expose: the database rejects both.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import Config, CurrentUser, DbSession, Now, StaffUser
from app.models.booking import Booking, BookingEvent
from app.models.enums import BookingStatus
from app.repositories.booking_search import has_passed, search_bookings
from app.schemas.booking import (
    BookingCancel,
    BookingCreate,
    BookingEventOut,
    BookingOut,
    BookingSettle,
    BookingWithTimeline,
    CancelResult,
    MemberSummary,
    NoteCreate,
)
from app.schemas.booking_search import (
    BookingListItem,
    BookingSort,
    SortDirection,
)
from app.schemas.common import Page
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _to_out(booking: Booking) -> BookingOut:
    return BookingOut(
        id=booking.id,
        session_id=booking.session_id,
        status=booking.status,
        booked_at=booking.booked_at,
        cancelled_at=booking.cancelled_at,
        settled_at=booking.settled_at,
        member=MemberSummary.model_validate(booking.member),
    )


def _event_to_out(event: BookingEvent) -> BookingEventOut:
    return BookingEventOut(
        id=event.id,
        event_type=event.event_type,
        old_status=event.old_status,
        new_status=event.new_status,
        note=event.note,
        actor_name=event.actor.full_name if event.actor is not None else None,
        is_system=event.is_system,
        occurred_at=event.occurred_at,
    )


@router.get("", response_model=Page[BookingListItem], summary="Find bookings")
async def list_bookings(
    db: DbSession,
    viewer: CurrentUser,
    settings: Config,
    now: Now,
    q: str | None = Query(default=None, max_length=100, description="Match member name or email."),
    class_id: uuid.UUID | None = Query(default=None),
    session_id: uuid.UUID | None = Query(default=None),
    status_filter: BookingStatus | None = Query(default=None, alias="status"),
    date_from: dt.date | None = Query(
        default=None, description="Earliest class date, in the studio's timezone."
    ),
    date_to: dt.date | None = Query(
        default=None, description="Latest class date. The whole day is included."
    ),
    sort: BookingSort = Query(default=BookingSort.BOOKED_AT),
    direction: SortDirection = Query(default=SortDirection.DESC),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[BookingListItem]:
    """Goal 6, in one server-side query.

    Scoped to what the viewer can see: staff get every booking, an instructor gets
    only those on sessions they lead or co-instruct. The filter is composed into
    the SQL, so an instructor does not receive rows that are then hidden — the
    rows are never selected.

    ``date_from`` and ``date_to`` bound the *class dates*, inclusive of both ends,
    read in the studio's timezone — the same meaning those two words have on the
    sessions endpoint.
    """
    result = await search_bookings(
        db,
        viewer=viewer,
        tz=settings.tz,
        search=q,
        class_id=class_id,
        session_id=session_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )

    items = [
        BookingListItem(
            id=row.booking.id,
            status=row.booking.status,
            booked_at=row.booking.booked_at,
            member_id=row.member.id,
            member_name=row.member.full_name,
            member_email=row.member.email,
            session_id=row.session.id,
            session_starts_at=row.session.starts_at,
            session_date=row.session.starts_at.astimezone(settings.tz).date(),
            session_start_time=row.session.starts_at.astimezone(settings.tz).time(),
            class_id=row.studio_class.id,
            class_title=row.studio_class.title,
            session_has_passed=has_passed(row.session, now),
        )
        for row in result.rows
    ]
    return Page[BookingListItem](items=items, total=result.total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book a member onto a session",
)
async def create_booking(
    payload: BookingCreate,
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
) -> BookingOut:
    """Succeeds directly to Booked if there is capacity, or Waitlisted if full.

    Rejected with an explanation when the member's membership has expired, the
    class is archived, the session has already started, or the member already has
    a place on it.
    """
    service = BookingService(db, settings)
    booking = await service.create(
        session_id=payload.session_id,
        member_id=payload.member_id,
        actor=staff,
        now=now,
        note=payload.note,
    )
    await db.commit()
    return _to_out(await service.get(booking.id))


@router.post(
    "/{booking_id}/cancel",
    response_model=CancelResult,
    summary="Cancel a booking",
)
async def cancel_booking(
    booking_id: uuid.UUID,
    payload: BookingCancel,
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
) -> CancelResult:
    """Cancelling a Booked booking promotes the earliest eligible waitlisted member.

    That happens in the same transaction, so a freed seat is never left unfilled
    while someone is waiting for it. The response says who was promoted, because
    from the session's seat count alone a refilled seat and an unfreed one look
    identical.
    """
    service = BookingService(db, settings)
    booking, promoted = await service.cancel(booking_id, actor=staff, now=now, note=payload.note)
    await db.commit()

    return CancelResult(
        booking=_to_out(await service.get(booking.id)),
        promoted=(_to_out(await service.get(promoted.id)) if promoted is not None else None),
    )


@router.post(
    "/{booking_id}/settle",
    response_model=BookingOut,
    summary="Record attendance",
)
async def settle_booking(
    booking_id: uuid.UUID,
    payload: BookingSettle,
    db: DbSession,
    settings: Config,
    now: Now,
    viewer: CurrentUser,
) -> BookingOut:
    """Mark a Booked booking as Attended or Absent, once the session has started.

    Not restricted to staff: the brief asks instructors to record who actually
    showed up. The narrower check — their own sessions only — is applied inside
    the service, under the session lock.
    """
    service = BookingService(db, settings)
    booking = await service.settle(
        booking_id,
        attended=payload.attended,
        actor=viewer,
        now=now,
        note=payload.note,
    )
    await db.commit()
    return _to_out(await service.get(booking.id))


@router.post(
    "/{booking_id}/notes",
    response_model=BookingEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a note to a booking",
)
async def add_note(
    booking_id: uuid.UUID,
    payload: NoteCreate,
    db: DbSession,
    settings: Config,
    now: Now,
    viewer: CurrentUser,
) -> BookingEventOut:
    """Notes are timeline entries, not a field.

    Goal 9 does not allow anything in the timeline to be edited, and a note kept
    as a column would be overwritten by the next one.
    """
    service = BookingService(db, settings)
    await service.add_note(booking_id, note=payload.note, actor=viewer, now=now)
    await db.commit()

    _booking, events = await service.timeline(booking_id, viewer)
    return _event_to_out(events[-1])


@router.get(
    "/{booking_id}/timeline",
    response_model=BookingWithTimeline,
    summary="The booking's history",
)
async def get_timeline(
    booking_id: uuid.UUID,
    db: DbSession,
    settings: Config,
    viewer: CurrentUser,
) -> BookingWithTimeline:
    """Goal 9: when it was created, every status change with old and new status and
    who made it, and any notes.

    The booking comes back with its events rather than the events alone. A history
    has to say whose it is to be a history at all, and the alternative — a second
    request to identify the booking — does not exist: there is no endpoint that
    fetches one booking by id, and adding one to serve a screen that already has
    the data would be the wrong shape.

    There is deliberately no endpoint to edit or delete an entry — not even for
    staff. The database rejects both operations, so such an endpoint could only
    ever return an error.
    """
    booking, events = await BookingService(db, settings).timeline(booking_id, viewer)
    return BookingWithTimeline(
        **_to_out(booking).model_dump(),
        events=[_event_to_out(e) for e in events],
    )
