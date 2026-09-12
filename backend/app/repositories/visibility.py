"""Row-level visibility, expressed as SQL.

Goal 1 says an instructor "can only see and act on sessions where they are the
primary instructor or a co-instructor", and that the difference "must be enforced
on the server". This is the mechanism for reads.

It is a *filter composed into the query*, not a check applied to the results. The
distinction matters: an instructor cannot read a booking on someone else's session
because the SQL never selects the row — not because a handler remembered to look
afterwards. A forgotten post-fetch check leaks data; a forgotten filter returns
nothing, which is noticed immediately.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.sql.elements import BooleanClauseList

from app.models.booking import Booking
from app.models.class_session import ClassSession, SessionCoInstructor
from app.models.enums import UserRole
from app.models.member import Member
from app.models.user import User


def visible_sessions_clause(user: User) -> ColumnElement[bool] | BooleanClauseList:
    """A WHERE clause restricting ``sessions`` to what this user may see.

    Staff see everything. An instructor sees the union of the sessions they lead
    and the sessions they co-instruct — which is exactly the single list goal 5
    asks for, so no separate "my sessions" endpoint is needed.
    """
    if user.role is UserRole.STAFF:
        return true()

    return or_(
        ClassSession.primary_instructor_id == user.id,
        ClassSession.id.in_(
            select(SessionCoInstructor.session_id).where(SessionCoInstructor.user_id == user.id)
        ),
    )


def can_access_session(
    user: User, session: ClassSession, co_instructor_ids: set[uuid.UUID]
) -> bool:
    """The same rule, evaluated in Python.

    Used by write paths, which have already loaded and locked the session row and
    need a yes/no rather than a filter. Kept beside the SQL version so the two
    cannot drift apart unnoticed.
    """
    if user.role is UserRole.STAFF:
        return True
    return session.primary_instructor_id == user.id or user.id in co_instructor_ids


def visible_members_clause(user: User) -> ColumnElement[bool] | BooleanClauseList:
    """A WHERE clause restricting ``members`` to the people this user may see.

    Staff see the whole binder — goal 1 gives them the membership records. An
    instructor sees the people who have a booking on a session they can see.

    It is defined in terms of ``visible_sessions_clause`` rather than repeating
    the rule, and that is the point: the set of members an instructor can read is
    derived from the set of bookings they can already read, so the roster and the
    directory cannot disagree about who exists. A name visible on a register and
    missing from the directory would be a worse bug than either behaviour on its
    own.

    Booking status is deliberately not filtered. Somebody who booked a class and
    cancelled still appears on that session's timeline, which the instructor can
    already open, so hiding the member record would conceal nothing and only
    produce a dangling name.

    Soft-deleted sessions are excluded, matching every other read in the system:
    a deleted session's bookings are cancelled with it and it is not part of
    anybody's teaching history.
    """
    if user.role is UserRole.STAFF:
        return true()

    return Member.id.in_(
        select(Booking.member_id)
        .join(ClassSession, ClassSession.id == Booking.session_id)
        .where(
            ClassSession.deleted_at.is_(None),
            visible_sessions_clause(user),
        )
    )
