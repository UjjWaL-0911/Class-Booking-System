"""Classes — the template a session is scheduled from.

Named ``StudioClass`` because ``class`` is a Python keyword. The table is
``classes``, which is what the brief calls it.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.columns import Str, UuidPk

if TYPE_CHECKING:
    from app.models.class_session import ClassSession


class StudioClass(Base, TimestampMixin):
    """A class the studio offers: title, discipline, and the defaults its sessions
    inherit (goal 2)."""

    __tablename__ = "classes"

    id: Mapped[UuidPk]
    title: Mapped[Str]
    description: Mapped[Str] = mapped_column(server_default="")

    # Freeform (yoga, spin, salsa). Nothing in the ten goals needs disciplines to
    # be a managed list, so a lookup table would be structure without a purpose.
    discipline: Mapped[Str]

    # Copied onto each new session, then independent — the brief requires
    # per-session overrides, so this is a default rather than a live reference.
    default_duration_min: Mapped[int] = mapped_column(Integer)
    default_capacity: Mapped[int] = mapped_column(Integer)

    # Archiving hides the class from default views without destroying its sessions
    # or bookings, and is reversed by clearing this column. It also stops new
    # bookings: a class no longer offered should not take sign-ups, though people
    # already booked keep their place.
    archived_at: Mapped[dt.datetime | None]

    sessions: Mapped[list[ClassSession]] = relationship(
        back_populates="studio_class", lazy="raise_on_sql"
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
        CheckConstraint("default_duration_min > 0", name="duration_positive"),
        CheckConstraint("default_capacity > 0", name="capacity_positive"),
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
