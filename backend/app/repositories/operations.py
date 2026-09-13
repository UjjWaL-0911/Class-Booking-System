"""Two operational reports: how hard the rooms work, and what the instructors are owed.

Neither is one of the ten goals — they are the "room utilisation reporting" and
"instructor payroll" stretch ideas, recorded as deliberate additions in
``decisions.md``.

They share a file because they share a shape: one grouped aggregate over `sessions`
in a date range, scoped by the same visibility rule as everything else. Splitting
them into two modules would be two places to keep that scoping correct.

Both count **scheduled** sessions rather than attended ones, which is a decision
rather than a shortcut. A room is occupied whether or not anybody turns up, and an
instructor who taught to an empty room still taught. Tying either figure to
attendance would make them move when a register is marked late, which is not what
either question is asking.
"""

from __future__ import annotations

import datetime as dt
from typing import NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc
from app.models.class_session import ClassSession
from app.models.enums import UserRole
from app.models.room import Room
from app.models.user import User
from app.repositories.visibility import visible_sessions_clause


class RoomUsage(NamedTuple):
    room_id: str
    room_name: str
    sessions: int
    minutes_booked: int


class InstructorPay(NamedTuple):
    instructor_id: str
    instructor_name: str
    sessions_taught: int
    minutes_taught: int
    session_rate_minor: int | None
    total_minor: int | None


def _window(date_from: dt.date, date_to: dt.date, tz: ZoneInfo) -> tuple[dt.datetime, dt.datetime]:
    """The range as instants, in the studio's timezone.

    Converted once here rather than cast per row, for the same two reasons the
    bookings list does it: a cast cannot use the index on ``starts_at``, and it
    would bucket by UTC days — filing a 07:00 Kolkata class under the previous
    date, which is exactly the kind of error that makes a monthly total quietly
    wrong at both ends.
    """
    return (
        to_utc(date_from, dt.time.min, tz),
        to_utc(date_to + dt.timedelta(days=1), dt.time.min, tz),
    )


async def room_utilisation(
    db: AsyncSession,
    *,
    viewer: User,
    tz: ZoneInfo,
    date_from: dt.date,
    date_to: dt.date,
) -> list[RoomUsage]:
    """Minutes each room was in use, busiest first.

    Every room is returned, including the ones that were never used — an outer join
    rather than an inner one. A room that hosted nothing is the most interesting row
    in a utilisation report, and an inner join would silently drop it.

    Duration comes from ``duration_min`` rather than ``ends_at - starts_at``. The two
    agree by construction, since a trigger maintains one from the other, but the
    integer is what staff typed and what a reader can check against the timetable.
    """
    start, end = _window(date_from, date_to, tz)
    in_window = and_(
        ClassSession.deleted_at.is_(None),
        ClassSession.starts_at >= start,
        ClassSession.starts_at < end,
        visible_sessions_clause(viewer),
    )

    rows = (
        await db.execute(
            select(
                Room.id,
                Room.name,
                func.count(ClassSession.id),
                func.coalesce(func.sum(ClassSession.duration_min), 0),
            )
            .select_from(Room)
            .outerjoin(ClassSession, and_(ClassSession.room_id == Room.id, in_window))
            .group_by(Room.id, Room.name)
            .order_by(func.coalesce(func.sum(ClassSession.duration_min), 0).desc(), Room.name)
        )
    ).all()

    return [
        RoomUsage(
            room_id=str(row[0]),
            room_name=row[1],
            sessions=int(row[2]),
            minutes_booked=int(row[3]),
        )
        for row in rows
    ]


async def instructor_pay(
    db: AsyncSession,
    *,
    viewer: User,
    tz: ZoneInfo,
    date_from: dt.date,
    date_to: dt.date,
) -> list[InstructorPay]:
    """What each instructor taught in the window, and what that comes to.

    **Only sessions they lead.** Co-instructing is help rather than delivery, and
    paying both people a full session rate for one class would be a policy decision
    this report has no business making on the studio's behalf. If the studio wants to
    pay co-instructors, that is a rate of its own and a conversation first.

    ``total_minor`` is null — not zero — when no rate has been set, because "we have
    not decided what to pay them" and "they are owed nothing" are different facts and
    a payroll report must not conflate them.

    Multiplied in SQL as integers throughout. Money never becomes a float here, and
    the only place it is divided by 100 is at the moment it is printed.
    """
    start, end = _window(date_from, date_to, tz)

    led = and_(
        ClassSession.primary_instructor_id == User.id,
        ClassSession.deleted_at.is_(None),
        ClassSession.starts_at >= start,
        ClassSession.starts_at < end,
        visible_sessions_clause(viewer),
    )
    taught = func.count(ClassSession.id)

    rows = (
        await db.execute(
            select(
                User.id,
                User.full_name,
                taught,
                func.coalesce(func.sum(ClassSession.duration_min), 0),
                User.session_rate_minor,
                # Integer arithmetic, and null when there is no rate — which is the
                # behaviour of `*` on a NULL operand, relied on deliberately here.
                cast(taught, Integer) * User.session_rate_minor,
            )
            .select_from(User)
            .outerjoin(ClassSession, led)
            .where(User.is_active.is_(True))
            .group_by(User.id, User.full_name, User.session_rate_minor)
            .having(taught > 0)
            .order_by(taught.desc(), User.full_name)
        )
    ).all()

    return [
        InstructorPay(
            instructor_id=str(row[0]),
            instructor_name=row[1],
            sessions_taught=int(row[2]),
            minutes_taught=int(row[3]),
            session_rate_minor=row[4],
            total_minor=row[5],
        )
        for row in rows
    ]


def is_teacher(user: User) -> bool:
    """Anybody who may be put in front of a class — either role.

    The same rule the session service applies when it validates an instructor id. A
    payroll report that listed only ``role='instructor'`` would omit a staff member
    who teaches on Thursdays, and they are the person most likely to notice.
    """
    return user.role in (UserRole.STAFF, UserRole.INSTRUCTOR)
