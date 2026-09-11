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

from app.models.class_session import ClassSession, SessionCoInstructor
from app.models.enums import UserRole
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
