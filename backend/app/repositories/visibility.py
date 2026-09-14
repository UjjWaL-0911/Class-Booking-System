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

from sqlalchemy import ColumnElement, false, or_, select, true
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

    **A member sees none of them, and that is not an oversight.** A member has
    every right to read the timetable — it is already published to strangers at
    ``/public/schedule`` — but not through *this* clause, because the endpoints it
    guards return ``SessionOut``: the instructor's email address, the room id, the
    session's ``version`` and four booking counts. ``PublicSession`` exists
    precisely so that audience gets a shape built for it rather than a filtered
    copy of somebody else's, and a member is that audience. Returning ``false()``
    here means the staff session surface cannot leak to them however it is edited
    later; what a member may read has its own model and its own endpoints.
    """
    if user.role is UserRole.STAFF:
        return true()
    if user.role is UserRole.MEMBER:
        return false()

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

    **False for a member**, always. This gate protects settling attendance and
    annotating a booking — things done *to* a session by whoever runs it. A member
    booking their own place is a different act with its own rules, and giving it a
    route through here would mean loosening the gate that stops one instructor
    marking another's register.
    """
    if user.role is UserRole.STAFF:
        return True
    if user.role is UserRole.MEMBER:
        return False
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

    **A member sees exactly one member: themselves.** Written as a condition on
    ``user_id`` rather than inherited from the instructor branch below, which
    would have given them "every member who booked a session you teach" — empty
    today, and silently wrong the day a member is also an instructor. The rule
    here is whose record it is, not which sessions are visible.
    """
    if user.role is UserRole.STAFF:
        return true()
    if user.role is UserRole.MEMBER:
        return Member.user_id == user.id

    return Member.id.in_(
        select(Booking.member_id)
        .join(ClassSession, ClassSession.id == Booking.session_id)
        .where(
            ClassSession.deleted_at.is_(None),
            visible_sessions_clause(user),
        )
    )
