"""Bulk generation of a weekly schedule (goal 7).

Four problems here are not obvious until you write it, and each shapes the design:

1. **Partial success cannot be done with plain inserts.** Goal 7 wants a report of
   what was created and what was skipped, but an exclusion-constraint violation
   aborts the whole transaction — insert twelve occurrences, have three conflict,
   and the other nine are gone too. Each candidate therefore goes in inside a
   SAVEPOINT.

2. **Savepoints are not free.** PostgreSQL caches only 64 subtransaction ids per
   backend; past that, every other backend has to consult ``pg_subtrans`` on
   visibility checks, which degrades the whole instance rather than just this
   query. So the batch is capped, and the advisory lock below removes the common
   cause of conflicts anyway.

3. **Concurrent generators would race and could deadlock.** Two staff generating
   into the same room contend on the GiST constraint, waiting on each other's
   uncommitted tuples in insertion order — with no natural lock ordering. A
   transaction-scoped advisory lock serialises the batch instead. It is the one
   advisory lock that is safe through a transaction pooler, because it is released
   by the transaction ending rather than by the connection being returned.

4. **Weekly recurrence is a local-time operation.** Adding seven days to a UTC
   instant drifts by an hour across a daylight-saving boundary: an 18:00 class
   silently becomes 17:00 for part of the year. Iterating over local dates and
   converting each occurrence independently is the only thing that keeps the
   wall-clock time the studio asked for.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NotFound, RuleViolation
from app.core.time import NonexistentLocalTime, to_utc
from app.models.class_session import ClassSession
from app.models.studio_class import StudioClass
from app.models.user import User
from app.schemas.recurrence import (
    RecurrenceCreate,
    SkippedOccurrence,
    SkipReason,
)


class GenerationOutcome:
    """The raw result, before it is turned into a response model."""

    def __init__(self) -> None:
        self.created: list[ClassSession] = []
        self.skipped: list[SkippedOccurrence] = []
        self.requested = 0


class RecurrenceService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def generate(self, payload: RecurrenceCreate) -> GenerationOutcome:
        studio_class = await self._class(payload.class_id)
        await self._require_active_instructor(payload.primary_instructor_id)
        await self._lock_resources(payload.room_id, payload.primary_instructor_id)

        outcome = GenerationOutcome()
        duration = payload.duration_min or studio_class.default_duration_min
        capacity = payload.capacity or studio_class.default_capacity

        occurrences = list(_weekly_dates(payload.date_from, payload.date_to, set(payload.weekdays)))
        outcome.requested = len(occurrences)
        if outcome.requested > self.settings.max_recurrence_candidates:
            raise RuleViolation(
                f"That pattern would generate {outcome.requested} sessions; "
                f"the limit is {self.settings.max_recurrence_candidates}. "
                f"Generate a shorter date range.",
                requested=outcome.requested,
                limit=self.settings.max_recurrence_candidates,
            )

        for day in occurrences:
            try:
                starts_at = to_utc(day, payload.start_time, self.settings.tz)
            except NonexistentLocalTime as exc:
                # Spring forward removes an hour. Shifting the class silently would
                # be worse than saying so.
                outcome.skipped.append(
                    SkippedOccurrence(
                        session_date=day,
                        start_time=payload.start_time,
                        reason=SkipReason.NONEXISTENT_LOCAL_TIME,
                        detail=str(exc),
                    )
                )
                continue

            ends_at = starts_at + dt.timedelta(minutes=duration)
            conflict = await self._find_conflict(
                payload.room_id, payload.primary_instructor_id, starts_at, ends_at
            )
            if conflict is not None:
                outcome.skipped.append(self._describe(day, payload, conflict))
                continue

            await self._try_insert(day, payload, starts_at, duration, capacity, outcome)

        return outcome

    # ---------------------------------------------------------------- insert

    async def _try_insert(
        self,
        day: dt.date,
        payload: RecurrenceCreate,
        starts_at: dt.datetime,
        duration: int,
        capacity: int,
        outcome: GenerationOutcome,
    ) -> None:
        """Insert one occurrence inside a savepoint.

        The pre-check above catches the ordinary case and produces a better
        message; this catches what it cannot — an occurrence colliding with an
        *earlier occurrence from this same batch*, which is not committed yet and
        so is invisible to a query but very much visible to the constraint.
        """
        session = ClassSession(
            class_id=payload.class_id,
            starts_at=starts_at,
            primary_instructor_id=payload.primary_instructor_id,
            room_id=payload.room_id,
            duration_min=duration,
            capacity=capacity,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(session)
                await self.db.flush()
        except IntegrityError as exc:
            constraint = str(exc.orig)
            reason = (
                SkipReason.INSTRUCTOR_BUSY if "instructor" in constraint else SkipReason.ROOM_BUSY
            )
            outcome.skipped.append(
                SkippedOccurrence(
                    session_date=day,
                    start_time=payload.start_time,
                    reason=reason,
                    detail=("Overlaps another session generated in this same batch."),
                )
            )
        else:
            outcome.created.append(session)

    # -------------------------------------------------------------- conflict

    async def _find_conflict(
        self,
        room_id: uuid.UUID,
        instructor_id: uuid.UUID,
        starts_at: dt.datetime,
        ends_at: dt.datetime,
    ) -> ClassSession | None:
        """Find an existing session this occurrence would collide with.

        Half-open overlap, matching the ``tstzrange`` semantics of the exclusion
        constraints: a session starting exactly when another ends does not clash,
        because back-to-back classes are normal.
        """
        overlaps = and_(ClassSession.starts_at < ends_at, ClassSession.ends_at > starts_at)
        return (
            await self.db.execute(
                select(ClassSession)
                .where(
                    ClassSession.deleted_at.is_(None),
                    overlaps,
                    or_(
                        ClassSession.room_id == room_id,
                        ClassSession.primary_instructor_id == instructor_id,
                    ),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    def _describe(
        self, day: dt.date, payload: RecurrenceCreate, conflict: ClassSession
    ) -> SkippedOccurrence:
        local = conflict.starts_at.astimezone(self.settings.tz)
        if conflict.primary_instructor_id == payload.primary_instructor_id:
            reason = SkipReason.INSTRUCTOR_BUSY
            detail = f"That instructor is already teaching at {local:%H:%M} on {local:%d %b %Y}."
        else:
            reason = SkipReason.ROOM_BUSY
            detail = f"That room is already booked at {local:%H:%M} on {local:%d %b %Y}."
        return SkippedOccurrence(
            session_date=day,
            start_time=payload.start_time,
            reason=reason,
            detail=detail,
            conflicting_session_id=conflict.id,
        )

    # --------------------------------------------------------------- locking

    async def _lock_resources(self, room_id: uuid.UUID, instructor_id: uuid.UUID) -> None:
        """Serialise batches that touch the same room or instructor.

        Transaction-scoped, so it is released by the commit or rollback rather than
        by the connection being handed back — which is what makes it safe through
        a transaction pooler, where a session-scoped advisory lock would leak onto
        an unrelated client.

        The two keys are taken in sorted order so two generators claiming the same
        pair cannot take them in opposite orders and deadlock.
        """
        keys = sorted(
            (
                _advisory_key("room", room_id),
                _advisory_key("instructor", instructor_id),
            )
        )
        for key in keys:
            await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    # --------------------------------------------------------------- helpers

    async def _class(self, class_id: uuid.UUID) -> StudioClass:
        studio_class = (
            await self.db.execute(select(StudioClass).where(StudioClass.id == class_id))
        ).scalar_one_or_none()
        if studio_class is None:
            raise NotFound("No such class.")
        if studio_class.archived_at is not None:
            raise RuleViolation("This class is archived. Restore it before generating sessions.")
        return studio_class

    async def _require_active_instructor(self, user_id: uuid.UUID) -> None:
        user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise NotFound("No such user.")
        if not user.is_active:
            raise RuleViolation("That account is deactivated.")


def _weekly_dates(date_from: dt.date, date_to: dt.date, weekdays: set[int]) -> Iterator[dt.date]:
    """Every matching local date in the range, inclusive of both ends.

    Iterating over *dates* rather than adding seven days to an instant is the whole
    point: a local date plus a local time is a wall-clock appointment, and each one
    converts to its own UTC instant. Adding 168 hours to a timestamp instead would
    move the class by an hour when the clocks change.
    """
    day = date_from
    while day <= date_to:
        if day.weekday() in weekdays:
            yield day
        day += dt.timedelta(days=1)


# Namespace constants, so a room and an instructor whose ids fold to the same
# number cannot serialise against each other for no reason.
_NAMESPACES = {"room": 1, "instructor": 2}
_GOLDEN = 0x9E37_79B9_7F4A_7C15  # odd multiplier, spreads the namespace bits


def _advisory_key(kind: str, value: uuid.UUID) -> int:
    """A stable signed 64-bit key for ``pg_advisory_xact_lock``.

    Derived arithmetically from the uuid rather than with ``hash()``. Python
    randomises string and tuple hashing per process (PYTHONHASHSEED), so a
    hash-based key would differ between workers — and the lock would appear to work
    in a single-process test while serialising nothing in production, which is the
    worst possible failure mode for a lock.
    """
    folded = (value.int ^ (_NAMESPACES[kind] * _GOLDEN)) & 0xFFFF_FFFF_FFFF_FFFF
    # pg_advisory_xact_lock takes a signed bigint.
    return folded - (1 << 64) if folded >= (1 << 63) else folded
