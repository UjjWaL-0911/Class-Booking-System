"""Session endpoints (goals 3 and 5).

Reads are scoped by ``visible_sessions_clause``, so ``GET /sessions`` returns
everything for staff and only their own sessions for an instructor. That is goal 5's
"one list of every session where they are the primary instructor or a
co-instructor" — the filter produces it, so a separate endpoint would just be a
second route to the same answer.

Writes are staff-only. Instructors gain one write path of their own when settlement
lands (goal 4), and that one is guarded inside the transaction rather than by a
dependency.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Query, Response, status

from app.core.config import Settings
from app.core.deps import Config, DbSession, Now, StaffUser, StudioUser
from app.models.class_session import ClassSession
from app.models.enums import BookingStatus
from app.schemas.class_session import (
    CoInstructorAdd,
    InstructorOut,
    SessionCreate,
    SessionOut,
    SessionUpdate,
)
from app.schemas.common import Page
from app.schemas.recurrence import GenerationReport, RecurrenceCreate
from app.services.recurrence_service import RecurrenceService
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_out(
    session: ClassSession,
    settings: Settings,
    *,
    counts: dict[BookingStatus, int],
) -> SessionOut:
    """Render a session in both wall-clock and instant form.

    Staff schedule in local time and the API stores UTC, so returning only one of
    the two would push the conversion — and the chance of getting it wrong — into
    every client.
    """
    local = session.starts_at.astimezone(settings.tz)
    return SessionOut(
        id=session.id,
        class_id=session.class_id,
        class_title=session.studio_class.title,
        discipline=session.studio_class.discipline,
        session_date=local.date(),
        start_time=local.time(),
        starts_at=session.starts_at,
        ends_at=session.ends_at,
        room_id=session.room_id,
        room_name=session.room.name,
        primary_instructor=InstructorOut.model_validate(session.primary_instructor),
        co_instructors=[
            InstructorOut.model_validate(link.user) for link in session.co_instructor_links
        ],
        duration_min=session.duration_min,
        capacity=session.capacity,
        booked_count=counts.get(BookingStatus.BOOKED, 0),
        waitlisted_count=counts.get(BookingStatus.WAITLISTED, 0),
        attended_count=counts.get(BookingStatus.ATTENDED, 0),
        no_show_count=counts.get(BookingStatus.NO_SHOW, 0),
        seats_remaining=max(session.capacity - counts.get(BookingStatus.BOOKED, 0), 0),
        version=session.version,
    )


async def _render(service: SessionService, session: ClassSession, settings: Settings) -> SessionOut:
    return _to_out(session, settings, counts=await service.counts(session.id))


@router.get("", response_model=Page[SessionOut], summary="List sessions")
async def list_sessions(
    db: DbSession,
    viewer: StudioUser,
    settings: Config,
    class_id: uuid.UUID | None = Query(
        default=None, description="Opening a class shows its sessions."
    ),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    include_archived_classes: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[SessionOut]:
    service = SessionService(db, settings)
    sessions, total = await service.list(
        viewer,
        class_id=class_id,
        date_from=date_from,
        date_to=date_to,
        include_archived_classes=include_archived_classes,
        limit=limit,
        offset=offset,
    )
    # One count query for the whole page rather than one per session.
    counts = await service.counts_for([s.id for s in sessions])
    return Page[SessionOut](
        items=[_to_out(s, settings, counts=counts[s.id]) for s in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=SessionOut, summary="Get one session")
async def get_session(
    session_id: uuid.UUID, db: DbSession, viewer: StudioUser, settings: Config
) -> SessionOut:
    service = SessionService(db, settings)
    return await _render(service, await service.get(session_id, viewer), settings)


@router.post(
    "",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a session",
)
async def create_session(
    payload: SessionCreate,
    db: DbSession,
    settings: Config,
    staff: StaffUser,
) -> SessionOut:
    """Duration and capacity default from the class when omitted (goal 3).

    A room or primary-instructor clash raises a GiST exclusion violation, which the
    error layer turns into a 409 naming the conflict rather than a 500.
    """
    service = SessionService(db, settings)
    session = await service.create(payload)
    await db.commit()
    return await _render(service, await service.get(session.id, staff), settings)


@router.patch("/{session_id}", response_model=SessionOut, summary="Edit a session")
async def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
) -> SessionOut:
    """Raising capacity fills the new seats from the waitlist, in this same
    transaction — so the response already reflects who moved up."""
    service = SessionService(db, settings)
    session = await service.update(session_id, payload, staff, now)
    await db.commit()
    return await _render(service, await service.get(session.id, staff), settings)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session",
)
async def delete_session(
    session_id: uuid.UUID,
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
) -> Response:
    """Soft-delete, cancelling any remaining active bookings.

    Each cancellation gets its own audit event marked as a system action, so the
    timeline explains why a member lost their place. The session row survives:
    goal 9 does not allow history to disappear because something was removed from
    the schedule.
    """
    await SessionService(db, settings).delete(session_id, staff, now)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{session_id}/co-instructors",
    response_model=SessionOut,
    summary="Add a co-instructor",
)
async def add_co_instructor(
    session_id: uuid.UUID,
    payload: CoInstructorAdd,
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
) -> SessionOut:
    """Goal 5: only studio staff may add a co-instructor.

    No overlap check — an instructor may co-instruct any number of sessions,
    including overlapping ones. Only the *primary* instructor is exclusive.
    """
    service = SessionService(db, settings)
    session = await service.add_co_instructor(session_id, payload.user_id, staff, now)
    await db.commit()
    return await _render(service, session, settings)


@router.delete(
    "/{session_id}/co-instructors/{user_id}",
    response_model=SessionOut,
    summary="Remove a co-instructor",
)
async def remove_co_instructor(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    settings: Config,
    staff: StaffUser,
) -> SessionOut:
    service = SessionService(db, settings)
    session = await service.remove_co_instructor(session_id, user_id, staff)
    await db.commit()
    return await _render(service, session, settings)


@router.post(
    "/generate",
    response_model=GenerationReport,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a weekly schedule",
)
async def generate_sessions(
    payload: RecurrenceCreate,
    db: DbSession,
    settings: Config,
    staff: StaffUser,
) -> GenerationReport:
    """Bulk-generate sessions from a weekly pattern (goal 7).

    Partial success by design: each occurrence is inserted inside a savepoint, so
    one conflict skips that occurrence rather than discarding the batch. The
    response says exactly what was created and what was skipped, naming the
    session each skipped occurrence collided with.

    The whole batch is one transaction, so the report and the database agree — if
    this returns, exactly the sessions it lists as created exist.
    """
    service = RecurrenceService(db, settings)
    outcome = await service.generate(payload)
    await db.commit()

    sessions = SessionService(db, settings)
    created = [
        await _render(sessions, await sessions.get(s.id, staff), settings) for s in outcome.created
    ]
    return GenerationReport(requested=outcome.requested, created=created, skipped=outcome.skipped)
