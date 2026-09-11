"""The booking lifecycle (goal 4) and its immutable timeline (goal 9).

This is the only place a booking's status changes, and the only place that decides
whether a member is Booked or Waitlisted. Everything else in the system is arranged
so that stays true.

**The concurrency rule.** Capacity is a per-session integer, so the session row is
the concurrency boundary. Every operation here begins by taking
``SELECT ... FROM sessions WHERE id = :id FOR UPDATE``. Operations on one session
then serialise; operations on different sessions stay fully parallel, which matches
how a studio is actually used. The count of Booked bookings is taken *under that
lock* and never cached, because a cached count is exactly the value that drifts.

Isolation is READ COMMITTED with an explicit lock rather than SERIALIZABLE:
serialisable isolation turns contention on the last seat into serialisation
failures and retries, which does the most work precisely when the system is
busiest. An explicit lock makes contenders queue, each doing its work once.

Lock order is always sessions → bookings. No I/O other than these statements
happens while the lock is held.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.errors import (
    Conflict,
    IllegalTransition,
    NotFound,
    PermissionDenied,
    RuleViolation,
)
from app.core.time import today
from app.db.transaction import apply_local_timeouts
from app.models.booking import Booking, BookingEvent
from app.models.class_session import ClassSession, SessionCoInstructor
from app.models.enums import BookingEventType, BookingStatus, UserRole
from app.models.member import Member
from app.models.studio_class import StudioClass
from app.models.user import User
from app.services.booking_events import record_event

_ACTIVE = BookingStatus.active()


class BookingService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # ------------------------------------------------------------- creating

    async def create(
        self,
        *,
        session_id: uuid.UUID,
        member_id: uuid.UUID,
        actor: User,
        now: dt.datetime,
        note: str | None = None,
    ) -> Booking:
        """Book a member onto a session.

        Goal 4: succeeds directly to Booked when there is capacity, or is placed as
        Waitlisted when the session is full. There is no confirmation step, which
        is why this system needs no seat-hold mechanism.
        """
        await apply_local_timeouts(self.db, self.settings)
        session = await self._lock_session(session_id)

        studio_class = await self._class_of(session)
        if studio_class.archived_at is not None:
            raise RuleViolation("This class has been archived and is not taking bookings.")
        if session.starts_at <= now:
            raise RuleViolation("This session has already started.")

        member = await self._member(member_id)
        if member.membership_expiry < today(self.settings.tz, now):
            raise RuleViolation(
                f"This member's membership expired on {member.membership_expiry:%d %b %Y}.",
                expired_on=member.membership_expiry.isoformat(),
            )

        if await self._active_booking(session_id, member_id) is not None:
            raise Conflict("This member already has a booking on this session.")

        # Counted under the lock. Any concurrent booking or cancellation on this
        # session is parked at its own lock acquisition until this transaction
        # commits, so this number cannot be stale.
        booked = await self._booked_count(session_id)
        status = BookingStatus.BOOKED if booked < session.capacity else BookingStatus.WAITLISTED

        booking = Booking(
            session_id=session_id,
            member_id=member_id,
            status=status,
            booked_at=now,
            created_by=actor.id,
        )
        self.db.add(booking)
        await self.db.flush()

        record_event(
            self.db,
            booking_id=booking.id,
            event_type=BookingEventType.CREATED,
            occurred_at=now,
            new_status=status,
            note=note,
            actor_user_id=actor.id,
        )
        await self.db.flush()
        return booking

    # ----------------------------------------------------------- cancelling

    async def cancel(
        self,
        booking_id: uuid.UUID,
        *,
        actor: User,
        now: dt.datetime,
        note: str | None = None,
    ) -> tuple[Booking, Booking | None]:
        """Cancel a booking, promoting from the waitlist if a seat was freed.

        Returns the cancelled booking and whoever was promoted, if anyone.

        The promotion happens in this same transaction, not as a follow-up: a seat
        can never be freed without the waitlist being considered, because there is
        no code path where one happens without the other.
        """
        await apply_local_timeouts(self.db, self.settings)
        booking = await self._booking(booking_id)
        session = await self._lock_session(booking.session_id)
        # Re-read under the lock — the row may have changed between the first read
        # and acquiring it.
        await self.db.refresh(booking)

        if booking.status not in _ACTIVE:
            raise IllegalTransition(
                f"Cannot cancel a booking that is already {booking.status.label}.",
                current_status=booking.status.value,
            )

        freed_a_seat = booking.status is BookingStatus.BOOKED
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
            note=note,
            actor_user_id=actor.id,
        )

        promoted = None
        if freed_a_seat:
            promoted = await self._promote_next(session, now)

        await self.db.flush()
        return booking, promoted

    async def _promote_next(self, session: ClassSession, now: dt.datetime) -> Booking | None:
        """Promote the earliest eligible waitlisted booking on this session.

        Two rules are enforced here rather than left implicit:

        * **A session that has already started promotes nobody.** A seat freeing
          mid-class means nothing.
        * **A member whose membership has expired is skipped, not promoted.** Goal
          4 blocks an expired member from *getting* a booking, and promoting one
          into a Booked seat would be the same outcome by a side door. They keep
          their place in the queue — renewing at the front desk is the likely next
          event — and a note records that a seat was offered and passed over, so
          the timeline explains what happened rather than showing an unexplained
          gap.
        """
        if session.starts_at <= now:
            return None

        candidates = (
            (
                await self.db.execute(
                    select(Booking)
                    .where(
                        Booking.session_id == session.id,
                        Booking.status == BookingStatus.WAITLISTED,
                    )
                    .order_by(Booking.booked_at, Booking.id)
                    .options(selectinload(Booking.member))
                )
            )
            .scalars()
            .all()
        )

        studio_today = today(self.settings.tz, now)
        for candidate in candidates:
            if candidate.member.membership_expiry < studio_today:
                record_event(
                    self.db,
                    booking_id=candidate.id,
                    event_type=BookingEventType.NOTE_ADDED,
                    occurred_at=now,
                    note=(
                        "A place became available but was passed over: this "
                        "membership expired on "
                        f"{candidate.member.membership_expiry:%d %b %Y}."
                    ),
                    is_system=True,
                )
                continue

            candidate.status = BookingStatus.BOOKED
            record_event(
                self.db,
                booking_id=candidate.id,
                event_type=BookingEventType.STATUS_CHANGED,
                occurred_at=now,
                old_status=BookingStatus.WAITLISTED,
                new_status=BookingStatus.BOOKED,
                note="Promoted from the waitlist after a cancellation.",
                is_system=True,
            )
            return candidate

        return None

    async def promote_to_fill(self, session: ClassSession, now: dt.datetime) -> list[Booking]:
        """Fill newly created seats after a capacity increase.

        Goal 4's principle is that a free seat never sits idle beside someone
        waiting, and a capacity increase creates seats exactly as a cancellation
        does. Bounded by the new capacity, so this cannot run away.
        """
        promoted: list[Booking] = []
        while True:
            booked = await self._booked_count(session.id)
            if booked >= session.capacity:
                break
            candidate = await self._promote_next(session, now)
            if candidate is None:
                break
            promoted.append(candidate)
            await self.db.flush()
        return promoted

    # ------------------------------------------------------------- settling

    async def settle(
        self,
        booking_id: uuid.UUID,
        *,
        attended: bool,
        actor: User,
        now: dt.datetime,
        note: str | None = None,
    ) -> Booking:
        """Record whether the member turned up (goal 4).

        This is the one write an instructor may perform, and only on their own
        sessions. That check happens here, inside the transaction and after the
        session row is locked — not as a dependency before it, which would leave a
        window in which they are removed as a co-instructor between the check and
        the write.
        """
        await apply_local_timeouts(self.db, self.settings)
        booking = await self._booking(booking_id)
        session = await self._lock_session(booking.session_id)
        await self._require_session_access(session, actor)
        await self.db.refresh(booking)

        if booking.status is not BookingStatus.BOOKED:
            raise IllegalTransition(
                f"Only a Booked booking can be settled; this one is {booking.status.label}.",
                current_status=booking.status.value,
            )
        if session.starts_at > now:
            raise IllegalTransition("This session has not started yet.")

        new_status = BookingStatus.ATTENDED if attended else BookingStatus.NO_SHOW
        booking.status = new_status
        booking.settled_at = now
        booking.settled_by = actor.id
        record_event(
            self.db,
            booking_id=booking.id,
            event_type=BookingEventType.STATUS_CHANGED,
            occurred_at=now,
            old_status=BookingStatus.BOOKED,
            new_status=new_status,
            note=note,
            actor_user_id=actor.id,
        )
        await self.db.flush()
        return booking

    async def add_note(
        self, booking_id: uuid.UUID, *, note: str, actor: User, now: dt.datetime
    ) -> BookingEvent:
        """Append a staff note to the timeline.

        Notes are events, not a mutable field on the booking. Goal 9 says nothing
        in the timeline can be edited or deleted, and a note stored as a column
        would be overwritten by the next one.
        """
        booking = await self._booking(booking_id)
        session = await self._lock_session(booking.session_id)
        await self._require_session_access(session, actor)

        event = record_event(
            self.db,
            booking_id=booking.id,
            event_type=BookingEventType.NOTE_ADDED,
            occurred_at=now,
            note=note,
            actor_user_id=actor.id,
        )
        await self.db.flush()
        return event

    # -------------------------------------------------------------- reading

    async def get(self, booking_id: uuid.UUID) -> Booking:
        """Load a booking with its member, for rendering a response.

        No visibility filter: every caller of this has already passed through an
        operation that checked access. Reading bookings *as a list* is goal 6 and
        applies the filter there.
        """
        return await self._booking(booking_id)

    async def timeline(
        self, booking_id: uuid.UUID, viewer: User
    ) -> tuple[Booking, Sequence[BookingEvent]]:
        """A booking and every event on it, oldest first (goal 9).

        The booking travels with its events because a history is unreadable
        without it: an entry saying ``waitlisted -> booked`` means nothing until
        you know whose booking it is and what it is for. The booking is already
        loaded here to authorize the read, so returning it costs nothing.

        Events are ordered by the identity column rather than by timestamp: two
        written in the same transaction share an ``occurred_at``, and a
        cancellation must never appear after the promotion it caused.
        """
        booking = await self._booking(booking_id)
        session = await self._lock_session(booking.session_id, for_update=False)
        await self._require_session_access(session, viewer)

        events = (
            (
                await self.db.execute(
                    select(BookingEvent)
                    .where(BookingEvent.booking_id == booking_id)
                    .order_by(BookingEvent.id)
                    .options(selectinload(BookingEvent.actor))
                )
            )
            .scalars()
            .all()
        )
        return booking, events

    # -------------------------------------------------------------- helpers

    async def _lock_session(
        self, session_id: uuid.UUID, *, for_update: bool = True
    ) -> ClassSession:
        """Take the per-session write lock. The single most important line here.

        ``for_update=False`` is for read paths, which need the row but must not
        block writers.
        """
        query = select(ClassSession).where(
            ClassSession.id == session_id, ClassSession.deleted_at.is_(None)
        )
        if for_update:
            query = query.with_for_update()
        session = (await self.db.execute(query)).scalar_one_or_none()
        if session is None:
            raise NotFound("No such session.")
        return session

    async def _booked_count(self, session_id: uuid.UUID) -> int:
        return (
            await self.db.execute(
                select(func.count())
                .select_from(Booking)
                .where(
                    Booking.session_id == session_id,
                    Booking.status == BookingStatus.BOOKED,
                )
            )
        ).scalar_one()

    async def _active_booking(self, session_id: uuid.UUID, member_id: uuid.UUID) -> Booking | None:
        return (
            await self.db.execute(
                select(Booking).where(
                    Booking.session_id == session_id,
                    Booking.member_id == member_id,
                    Booking.status.in_(_ACTIVE),
                )
            )
        ).scalar_one_or_none()

    async def _booking(self, booking_id: uuid.UUID) -> Booking:
        booking = (
            await self.db.execute(
                select(Booking)
                .where(Booking.id == booking_id)
                .options(selectinload(Booking.member))
            )
        ).scalar_one_or_none()
        if booking is None:
            raise NotFound("No such booking.")
        return booking

    async def _member(self, member_id: uuid.UUID) -> Member:
        member = (
            await self.db.execute(select(Member).where(Member.id == member_id))
        ).scalar_one_or_none()
        if member is None:
            raise NotFound("No such member.")
        return member

    async def _class_of(self, session: ClassSession) -> StudioClass:
        return (
            await self.db.execute(select(StudioClass).where(StudioClass.id == session.class_id))
        ).scalar_one()

    async def _require_session_access(self, session: ClassSession, user: User) -> None:
        """Row-level authorization for write paths.

        Neither a role check nor a read filter: an instructor may settle, but only
        on a session they lead or co-instruct.
        """
        if user.role is UserRole.STAFF:
            return
        if session.primary_instructor_id == user.id:
            return
        is_co = (
            await self.db.execute(
                select(SessionCoInstructor).where(
                    SessionCoInstructor.session_id == session.id,
                    SessionCoInstructor.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if is_co is None:
            raise PermissionDenied("You do not have access to this session.")
