"""Sessions — a single scheduled occurrence of a class — and their co-instructors.

Named ``ClassSession`` so it never gets confused with a SQLAlchemy ``Session``.
The table is ``sessions``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import FetchedValue

from app.db.base import Base, TimestampMixin
from app.db.columns import CreatedAt, UuidPk

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.room import Room
    from app.models.studio_class import StudioClass
    from app.models.user import User


class ClassSession(Base, TimestampMixin):
    """One scheduled occurrence of a class (goal 3).

    This row is also the concurrency boundary for the whole system: every
    operation that can change the number of Booked bookings or the waitlist takes
    ``SELECT ... FOR UPDATE`` on it first. Sessions are independent of one
    another, so that serialises what must be serialised and nothing else.
    """

    __tablename__ = "sessions"

    id: Mapped[UuidPk]
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="RESTRICT"))
    starts_at: Mapped[dt.datetime]

    # Derived from starts_at + duration_min, maintained by a BEFORE INSERT OR
    # UPDATE trigger rather than a generated column: generated columns require an
    # IMMUTABLE expression and `timestamptz + interval` is only STABLE, because an
    # interval's day and month parts resolve against the session TimeZone setting.
    # Verified on PostgreSQL 18.6 — see the platform-claims table in
    # architecture.md. FetchedValue tells SQLAlchemy the database supplies it.
    ends_at: Mapped[dt.datetime] = mapped_column(
        server_default=FetchedValue(), server_onupdate=FetchedValue()
    )

    # Any *active* user, not only role='instructor' — a staff member who also
    # teaches is a real case. Enforced in the service, since a CHECK constraint
    # cannot read another table.
    primary_instructor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"))

    # Copied from the class defaults at creation, independent thereafter.
    duration_min: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)

    # Soft delete: bookings and their audit trail must survive. Deleting a session
    # also cancels its remaining active bookings, each with its own audit event —
    # application logic rather than a cascade, precisely so the trail exists.
    deleted_at: Mapped[dt.datetime | None]

    studio_class: Mapped[StudioClass] = relationship(back_populates="sessions", lazy="raise_on_sql")
    room: Mapped[Room] = relationship(lazy="raise_on_sql")
    primary_instructor: Mapped[User] = relationship(
        back_populates="primary_sessions",
        foreign_keys=[primary_instructor_id],
        lazy="raise_on_sql",
    )
    bookings: Mapped[list[Booking]] = relationship(back_populates="session", lazy="raise_on_sql")
    co_instructor_links: Mapped[list[SessionCoInstructor]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="raise_on_sql"
    )

    # Optimistic concurrency for staff edits. Two things use it, and they are
    # different: SQLAlchemy's version_id_col catches two *concurrent transactions*
    # updating a row they both loaded, while the service separately compares the
    # version the *client* submitted — a stale edit form, which the ORM cannot see
    # because it was rendered in an earlier request.
    #
    # Booking operations rely on neither; they take SELECT ... FOR UPDATE on the
    # session row. See "Two locking strategies on one table" in schema.md.
    version: Mapped[int] = mapped_column(nullable=False, server_default="0")

    # Declared in the class body rather than on a mixin: __mapper_args__ resolves
    # by MRO, so a second mixin defining it would silently win and take the version
    # check with it. eager_defaults fetches trigger-maintained columns with
    # RETURNING, without which reading them after a write raises MissingGreenlet.
    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012

    __table_args__ = (
        CheckConstraint("duration_min > 0", name="duration_positive"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        # Sorting the bookings list by session joins here; no index on `bookings`
        # can serve that, because the sort key lives on this table.
        Index(
            "ix_sessions_starts_at",
            "starts_at",
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_sessions_class", "class_id"),
        # The two GiST exclusion constraints (no_room_overlap,
        # no_primary_instructor_overlap) are added in the migration: they need
        # tstzrange() over two columns, which SQLAlchemy cannot express here.
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class SessionCoInstructor(Base):
    """Many-to-many between sessions and instructors (goal 5).

    Co-instructors are deliberately exempt from the overlap constraint that
    applies to the primary instructor: the brief allows one instructor to be added
    to any number of sessions, including overlapping ones.
    """

    __tablename__ = "session_co_instructors"

    # CASCADE is safe here and nowhere else in this schema: these rows carry no
    # history worth keeping once the session is gone, and sessions are soft-deleted
    # in normal operation anyway.
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    added_at: Mapped[CreatedAt]

    session: Mapped[ClassSession] = relationship(
        back_populates="co_instructor_links",
        foreign_keys=[session_id],
        lazy="raise_on_sql",
    )
    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="raise_on_sql")

    __table_args__ = (
        PrimaryKeyConstraint("session_id", "user_id", name="pk_session_co_instructors"),
        # "Every session I am involved in" reads this by user.
        Index("ix_session_co_instructors_user", "user_id"),
    )
