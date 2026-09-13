"""Booking one member into a whole term of a class.

Not one of the ten goals — it is the "recurring bookings across an entire term"
stretch idea, and it is recorded as a deliberate addition in ``decisions.md``.

**It is deliberately the same shape as the recurring session generator (goal 7)**,
because it has the same problem: a bulk action over candidates that can each
individually fail, where aborting the batch on the first failure would be useless.
The generator solved it with a savepoint per candidate and a report of what was
created and what was skipped. This reuses that pattern rather than inventing a
second one, which is most of why it is cheap.

The one thing it does *not* reuse is the booking rules. Every candidate goes through
``BookingService.create`` — the same method the single-booking endpoint calls, with
the same lock, the same capacity decision, the same expiry check and the same audit
event. A bulk path with its own copy of those rules is a bulk path that eventually
disagrees with the single one, and the disagreement would be invisible until
somebody compared two members' histories.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import Conflict, NotFound, RuleViolation
from app.core.time import to_utc
from app.models.class_session import ClassSession
from app.models.enums import BookingStatus
from app.models.member import Member
from app.models.studio_class import StudioClass
from app.models.user import User
from app.repositories.visibility import visible_sessions_clause
from app.schemas.term_booking import (
    BookingSkipReason,
    TermBookingCreate,
    TermBookingOutcome,
    TermBookingReport,
)
from app.services.booking_service import BookingService

# The same ceiling the session generator uses, for the same reason: Postgres caches
# 64 subtransaction ids per backend, and past that every other backend pays for it
# on visibility checks. A term is a few dozen sessions; 200 is far beyond that and
# well short of the point where savepoints start costing the whole instance.
MAX_SESSIONS = 200


class TermBookingService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def book_term(
        self,
        payload: TermBookingCreate,
        *,
        actor: User,
        now: dt.datetime,
    ) -> TermBookingReport:
        """Book the member into every matching session, reporting each outcome.

        Runs in one transaction, so the report and the database agree: if the
        request succeeds, exactly the bookings listed as taken exist. A savepoint
        around each candidate is what lets one refusal roll back alone instead of
        taking the other thirteen with it.
        """
        await self._require_member(payload.member_id)
        sessions = await self._candidates(payload, actor)

        booked: list[TermBookingOutcome] = []
        waitlisted: list[TermBookingOutcome] = []
        skipped: list[TermBookingOutcome] = []

        service = BookingService(self.db, self.settings)
        for session in sessions:
            outcome = await self._book_one(service, session, payload, actor=actor, now=now)
            if outcome.reason is not None:
                skipped.append(outcome)
            elif outcome.waitlisted:
                waitlisted.append(outcome)
            else:
                booked.append(outcome)

        return TermBookingReport(
            requested=len(sessions),
            booked=booked,
            waitlisted=waitlisted,
            skipped=skipped,
        )

    async def _book_one(
        self,
        service: BookingService,
        session: ClassSession,
        payload: TermBookingCreate,
        *,
        actor: User,
        now: dt.datetime,
    ) -> TermBookingOutcome:
        """One candidate, inside a savepoint.

        The exceptions caught here are the booking rules speaking, not failures:
        ``RuleViolation`` is an expired membership, a started session or an archived
        class, and ``Conflict`` is a member already holding a place. Each rolls back
        this candidate only, and becomes a line in the report naming the rule.

        ``IntegrityError`` is caught separately because it arrives from the database
        rather than the service — the partial unique index refusing a second active
        booking. It means the same thing as the ``Conflict`` above and is reported
        the same way.
        """
        local = session.starts_at.astimezone(self.settings.tz)
        outcome = TermBookingOutcome(
            session_id=session.id,
            session_date=local.date(),
            start_time=local.time(),
        )

        try:
            async with self.db.begin_nested():
                booking = await service.create(
                    session_id=session.id,
                    member_id=payload.member_id,
                    actor=actor,
                    now=now,
                    note=payload.note,
                )
        except Conflict as exc:
            outcome.reason = BookingSkipReason.ALREADY_BOOKED
            outcome.detail = str(exc)
            return outcome
        except IntegrityError:
            outcome.reason = BookingSkipReason.ALREADY_BOOKED
            outcome.detail = "This member already has a booking on this session."
            return outcome
        except RuleViolation as exc:
            outcome.reason = _reason_for(str(exc))
            outcome.detail = str(exc)
            return outcome

        outcome.booking_id = booking.id
        outcome.waitlisted = booking.status is BookingStatus.WAITLISTED
        return outcome

    async def _candidates(
        self, payload: TermBookingCreate, viewer: User
    ) -> Sequence[ClassSession]:
        """Sessions of this class in the range, oldest first.

        **This books into sessions that already exist; it never creates one.** That
        is the line between this and the goal 7 generator, and keeping it sharp is
        what stops a typo in a date range quietly filling the timetable.

        Ordered by start time so the report reads as a term, and so the waitlist
        order a member ends up with matches the order the classes run in.

        The visibility clause is applied even though the endpoint is staff-only. It
        costs nothing, and a scoping rule that is present on every other session
        query and absent from one is how the exception becomes the bug.
        """
        tz = self.settings.tz
        query = (
            select(ClassSession)
            .where(
                ClassSession.class_id == payload.class_id,
                ClassSession.deleted_at.is_(None),
                visible_sessions_clause(viewer),
                ClassSession.starts_at >= to_utc(payload.date_from, dt.time.min, tz),
                ClassSession.starts_at
                < to_utc(payload.date_to + dt.timedelta(days=1), dt.time.min, tz),
            )
            .order_by(ClassSession.starts_at)
            .limit(MAX_SESSIONS)
        )
        sessions = list((await self.db.execute(query)).scalars().all())

        if payload.weekdays is None:
            return sessions

        # Filtered on the **local** weekday. A 07:00 class in Asia/Kolkata is the
        # previous day in UTC, so filtering on the stored instant would drop every
        # Monday morning from a Monday pattern.
        wanted = set(payload.weekdays)
        return [s for s in sessions if s.starts_at.astimezone(tz).weekday() in wanted]

    async def _require_member(self, member_id: uuid.UUID) -> Member:
        member = (
            await self.db.execute(select(Member).where(Member.id == member_id))
        ).scalar_one_or_none()
        if member is None:
            raise NotFound("No such member.")
        return member

    async def require_class(self, class_id: uuid.UUID) -> StudioClass:
        """Fail on a class that does not exist, rather than reporting zero sessions.

        "Nothing matched" and "that class is not a thing" look identical in a report
        of length zero, and only one of them is worth a person's attention.
        """
        studio_class = (
            await self.db.execute(select(StudioClass).where(StudioClass.id == class_id))
        ).scalar_one_or_none()
        if studio_class is None:
            raise NotFound("No such class.")
        return studio_class


def _reason_for(message: str) -> BookingSkipReason:
    """Map the rule's own sentence onto a machine-readable reason.

    Matching on message text is not something to be proud of, and it is confined to
    this one function so that it is obvious and greppable. The alternative — giving
    every ``RuleViolation`` a code — is the better fix and is a wider change than
    this feature should make on its own.
    """
    lowered = message.lower()
    if "expired" in lowered:
        return BookingSkipReason.MEMBERSHIP_EXPIRED
    if "already started" in lowered:
        return BookingSkipReason.SESSION_STARTED
    if "archived" in lowered:
        return BookingSkipReason.CLASS_ARCHIVED
    return BookingSkipReason.REFUSED
