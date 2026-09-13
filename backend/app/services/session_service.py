"""Session scheduling (goal 3) and co-instructors (goal 5).

Two things here are more than CRUD:

* **Deleting a session** is a soft delete that also cancels every remaining active
  booking, each with its own audit event. It is application logic rather than a
  database cascade precisely so that trail exists — goal 9 does not allow a
  booking to change state without a record of why.
* **Overlap** is enforced by two GiST exclusion constraints rather than by a
  read-then-write check here, which could not be race-free. This service's job is
  to turn the resulting integrity error into a message naming the conflict.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.errors import Conflict, NotFound, PermissionDenied, RuleViolation
from app.core.time import to_utc
from app.db.transaction import apply_local_timeouts, lock_session_row
from app.models.booking import Booking
from app.models.class_session import ClassSession, SessionCoInstructor
from app.models.enums import BookingEventType, BookingStatus
from app.models.studio_class import StudioClass
from app.models.user import User
from app.repositories.visibility import visible_sessions_clause
from app.schemas.class_session import SessionCreate, SessionUpdate
from app.services.booking_events import record_event


class SessionService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # -------------------------------------------------------------- reading

    def _base_query(self, viewer: User) -> Select[tuple[ClassSession]]:
        """Every read starts here, so the visibility filter cannot be forgotten."""
        return (
            select(ClassSession)
            .where(ClassSession.deleted_at.is_(None))
            .where(visible_sessions_clause(viewer))
            .options(
                selectinload(ClassSession.studio_class),
                selectinload(ClassSession.room),
                selectinload(ClassSession.primary_instructor),
                selectinload(ClassSession.co_instructor_links).selectinload(
                    SessionCoInstructor.user
                ),
            )
        )

    async def list(
        self,
        viewer: User,
        *,
        class_id: uuid.UUID | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        include_archived_classes: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[ClassSession], int]:
        """List sessions this viewer may see.

        For an instructor this *is* goal 5's "one list of every session where they
        are the primary instructor or a co-instructor" — the filter produces it, so
        a separate endpoint would be a second way to get the same answer.
        """
        query = self._base_query(viewer)

        if class_id is not None:
            query = query.where(ClassSession.class_id == class_id)
        if not include_archived_classes:
            query = query.join(StudioClass).where(StudioClass.archived_at.is_(None))
        if date_from is not None:
            query = query.where(
                ClassSession.starts_at >= to_utc(date_from, dt.time.min, self.settings.tz)
            )
        if date_to is not None:
            # Inclusive of the whole end day, which is what a date range means to
            # someone filling in a form.
            query = query.where(
                ClassSession.starts_at
                < to_utc(date_to + dt.timedelta(days=1), dt.time.min, self.settings.tz)
            )

        total = (
            await self.db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
        ).scalar_one()

        rows = (
            (
                await self.db.execute(
                    query.order_by(ClassSession.starts_at, ClassSession.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def get(self, session_id: uuid.UUID, viewer: User) -> ClassSession:
        """Fetch one session, subject to the same visibility filter.

        A session the viewer cannot see is reported as missing rather than
        forbidden: telling an instructor that a session exists but is not theirs
        leaks its existence.
        """
        session = (
            (await self.db.execute(self._base_query(viewer).where(ClassSession.id == session_id)))
            .scalars()
            .unique()
            .one_or_none()
        )
        if session is None:
            raise NotFound("No such session.")
        return session

    async def counts_for(
        self, session_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, dict[BookingStatus, int]]:
        """Booking counts by status, for many sessions in one query.

        Batched rather than per-session because the timetable asks for a whole
        week at once: counting inside the render loop turned one page into one
        query per class, which is the classic N+1 and is at its worst on exactly
        the screen that lists the most.

        Read-only and unlocked — this is for display. The booking service counts
        again under ``SELECT ... FOR UPDATE`` when the number has to be *decided*
        on, because a count taken without the lock is already out of date.
        """
        if not session_ids:
            return {}

        rows = (
            await self.db.execute(
                select(Booking.session_id, Booking.status, func.count())
                .where(Booking.session_id.in_(session_ids))
                .group_by(Booking.session_id, Booking.status)
            )
        ).all()

        counts: dict[uuid.UUID, dict[BookingStatus, int]] = {
            session_id: {} for session_id in session_ids
        }
        for session_id, booking_status, count in rows:
            counts[session_id][booking_status] = count
        return counts

    async def counts(self, session_id: uuid.UUID) -> dict[BookingStatus, int]:
        """Booking counts by status for one session."""
        return (await self.counts_for([session_id]))[session_id]

    # -------------------------------------------------------------- writing

    async def create(self, payload: SessionCreate) -> ClassSession:
        studio_class = (
            await self.db.execute(select(StudioClass).where(StudioClass.id == payload.class_id))
        ).scalar_one_or_none()
        if studio_class is None:
            raise NotFound("No such class.")
        if studio_class.archived_at is not None:
            raise RuleViolation("This class is archived. Restore it before scheduling sessions.")

        await self._require_active_instructor(payload.primary_instructor_id)

        session = ClassSession(
            class_id=payload.class_id,
            starts_at=to_utc(payload.session_date, payload.start_time, self.settings.tz),
            primary_instructor_id=payload.primary_instructor_id,
            room_id=payload.room_id,
            # Copy-on-create, not a live reference: goal 3 requires per-session
            # overrides, so a later change to the class must not silently move
            # sessions that were already scheduled.
            duration_min=payload.duration_min or studio_class.default_duration_min,
            capacity=payload.capacity or studio_class.default_capacity,
        )
        self.db.add(session)
        # Flush here so an overlap violation surfaces now, as a 409 naming the
        # conflict, rather than at commit where the cause is harder to attribute.
        await self.db.flush()
        return session

    async def update(
        self, session_id: uuid.UUID, payload: SessionUpdate, viewer: User, now: dt.datetime
    ) -> ClassSession:
        """Edit a session.

        Almost every field here is an ordinary optimistic update: check the
        ``version``, assign, flush. **Capacity is not**, because it participates in
        the booking invariant — raising it creates seats, and a seat that exists
        while somebody is waiting for it has to be filled.

        So a request that touches capacity takes the same ``FOR UPDATE`` a booking
        takes, and it takes it *before* the row is read. Locking after the version
        check would validate against a row another transaction could still be
        changing; locking first means the version this method compares is the
        version nobody else can move.
        """
        touches_capacity = payload.capacity is not None
        if touches_capacity:
            await apply_local_timeouts(self.db, self.settings)
            await lock_session_row(self.db, session_id)

        session = await self.get(session_id, viewer)

        if session.version != payload.version:
            raise Conflict(
                "This session was changed by someone else. Reload and try again.",
                expected=payload.version,
                actual=session.version,
            )

        if payload.primary_instructor_id is not None:
            await self._require_active_instructor(payload.primary_instructor_id)
            await self._require_not_co_instructor(session_id, payload.primary_instructor_id)
            session.primary_instructor_id = payload.primary_instructor_id

        if payload.session_date is not None or payload.start_time is not None:
            local = session.starts_at.astimezone(self.settings.tz)
            session.starts_at = to_utc(
                payload.session_date or local.date(),
                payload.start_time or local.timetz().replace(tzinfo=None),
                self.settings.tz,
            )

        if payload.room_id is not None:
            session.room_id = payload.room_id
        if payload.duration_min is not None:
            session.duration_min = payload.duration_min
        if payload.capacity is not None:
            await self._apply_capacity(session, payload.capacity, now)

        await self.db.flush()
        return session

    async def _apply_capacity(
        self, session: ClassSession, capacity: int, now: dt.datetime
    ) -> None:
        """Apply a capacity change. The caller holds the session row lock.

        **Down** is refused rather than allowed to ride: the deferred capacity
        trigger fires on writes to ``bookings``, not to ``sessions``, so nothing
        would catch the resulting oversell — and it would leave no record of who
        caused it. Making staff cancel explicitly means every removal has an actor
        and an audit event.

        **Up** fills the new seats from the waitlist. Goal 4's principle is that a
        free seat never sits idle beside somebody waiting, and raising capacity
        creates seats exactly as a cancellation does — the studio should not have to
        cancel and rebook a member to make the queue move.

        The promotion itself belongs to ``BookingService``: eligibility, ordering
        and the audit events are its rules, and a second implementation here would
        be a second set of rules to keep in step. The import is local to this method
        because the dependency runs only in this direction — the booking service
        knows nothing about session editing.
        """
        booked = (await self.counts(session.id)).get(BookingStatus.BOOKED, 0)
        if capacity < booked:
            raise Conflict(
                f"{booked} members are booked on this session. "
                f"Reduce capacity to {booked} or more, or cancel bookings first.",
                booked=booked,
                requested=capacity,
            )

        raised = capacity > session.capacity
        session.capacity = capacity
        if not raised:
            return

        # Flush so the promotion counts against the new capacity rather than the old.
        await self.db.flush()
        from app.services.booking_service import BookingService

        await BookingService(self.db, self.settings).promote_to_fill(session, now)

    async def delete(self, session_id: uuid.UUID, actor: User, now: dt.datetime) -> int:
        """Soft-delete a session and cancel what was booked on it.

        Returns the number of bookings cancelled. The session row survives so its
        bookings and their timelines remain readable — goal 9 does not allow
        history to disappear because a session was removed from the schedule.

        No waitlist promotion runs: the session is gone, so there is no seat to
        promote anyone into.
        """
        session = await self.get(session_id, actor)
        session.deleted_at = now

        active = (
            (
                await self.db.execute(
                    select(Booking).where(
                        Booking.session_id == session_id,
                        Booking.status.in_(BookingStatus.active()),
                    )
                )
            )
            .scalars()
            .all()
        )

        for booking in active:
            previous = booking.status
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            record_event(
                self.db,
                booking_id=booking.id,
                event_type=BookingEventType.STATUS_CHANGED,
                occurred_at=now,
                old_status=previous,
                new_status=BookingStatus.CANCELLED,
                note="Session was deleted.",
                is_system=True,
            )

        await self.db.flush()
        return len(active)

    # ------------------------------------------------------- co-instructors

    async def add_co_instructor(
        self, session_id: uuid.UUID, user_id: uuid.UUID, actor: User, now: dt.datetime
    ) -> ClassSession:
        session = await self.get(session_id, actor)
        await self._require_active_instructor(user_id)

        if session.primary_instructor_id == user_id:
            raise RuleViolation("That instructor already leads this session.")

        existing = (
            await self.db.execute(
                select(SessionCoInstructor).where(
                    SessionCoInstructor.session_id == session_id,
                    SessionCoInstructor.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise RuleViolation("That instructor is already a co-instructor here.")

        # Deliberately no overlap check: goal 5 allows one instructor to be added
        # to any number of sessions, and the exclusion constraint applies only to
        # the primary instructor.
        self.db.add(
            SessionCoInstructor(
                session_id=session_id,
                user_id=user_id,
                added_by=actor.id,
                added_at=now,
            )
        )
        await self.db.flush()
        return await self.get(session_id, actor)

    async def remove_co_instructor(
        self, session_id: uuid.UUID, user_id: uuid.UUID, actor: User
    ) -> ClassSession:
        session = await self.get(session_id, actor)
        link = (
            await self.db.execute(
                select(SessionCoInstructor).where(
                    SessionCoInstructor.session_id == session.id,
                    SessionCoInstructor.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            raise NotFound("That instructor is not a co-instructor on this session.")

        await self.db.delete(link)
        await self.db.flush()
        return await self.get(session_id, actor)

    # -------------------------------------------------------------- helpers

    async def _require_active_instructor(self, user_id: uuid.UUID) -> User:
        """Any active user may lead a session, not only role='instructor'.

        A staff member who also teaches is a real case, and a CHECK constraint
        cannot read another table — so this rule lives here.
        """
        user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise NotFound("No such user.")
        if not user.is_active:
            raise RuleViolation("That account is deactivated.")
        return user

    async def _require_not_co_instructor(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """A person cannot be both primary and co-instructor on one session."""
        clash = (
            await self.db.execute(
                select(SessionCoInstructor).where(
                    SessionCoInstructor.session_id == session_id,
                    SessionCoInstructor.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise RuleViolation(
                "That instructor is already a co-instructor on this session. "
                "Remove them as a co-instructor first."
            )

    async def require_access(self, session_id: uuid.UUID, actor: User) -> ClassSession:
        """Assert write access to a session, for paths an instructor may take.

        Called inside the transaction, after the session row is locked — not as a
        dependency before it. A check made before the lock leaves a window in which
        the instructor is removed as a co-instructor between the check and the
        write.
        """
        session = (
            await self.db.execute(
                select(ClassSession).where(
                    ClassSession.id == session_id,
                    ClassSession.deleted_at.is_(None),
                    visible_sessions_clause(actor),
                )
            )
        ).scalar_one_or_none()
        if session is None:
            raise PermissionDenied("You do not have access to this session.")
        return session
