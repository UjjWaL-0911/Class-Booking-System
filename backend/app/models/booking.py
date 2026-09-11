"""Bookings and their immutable timeline.

These two tables are the heart of the system, and the split between them is the
central modelling decision: ``booking_events`` is the authoritative, append-only
history (goal 9), while ``bookings`` carries a denormalised projection of the
current state so goals 6 and 8 can filter and aggregate without replaying a log
per row. The log is what happened; the column is what is true now.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.columns import CreatedAt, UuidPk
from app.models.enums import (
    BOOKING_EVENT_TYPE,
    BOOKING_STATUS,
    BookingEventType,
    BookingStatus,
)

if TYPE_CHECKING:
    from app.models.class_session import ClassSession
    from app.models.member import Member
    from app.models.user import User


class Booking(Base):
    """One member's place on one session (goal 4)."""

    __tablename__ = "bookings"

    id: Mapped[UuidPk]
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="RESTRICT"))
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    status: Mapped[BookingStatus] = mapped_column(BOOKING_STATUS)

    # Set once at creation and never changed. Drives two things: the "sort by
    # booked time" option in goal 6, and the waitlist order — the earliest
    # waitlisted booking is the one promoted when a seat frees.
    booked_at: Mapped[CreatedAt]

    cancelled_at: Mapped[dt.datetime | None]
    settled_at: Mapped[dt.datetime | None]

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    settled_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    session: Mapped[ClassSession] = relationship(back_populates="bookings", lazy="raise_on_sql")
    member: Mapped[Member] = relationship(back_populates="bookings", lazy="raise_on_sql")
    events: Mapped[list[BookingEvent]] = relationship(
        back_populates="booking",
        order_by="BookingEvent.id",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        # Counting Booked rows under the session lock, and finding the earliest
        # waitlisted booking to promote.
        Index("ix_bookings_session_status", "session_id", "status", "booked_at"),
        # Goal 6: status filter combined with sort by booked time.
        Index("ix_bookings_status_booked_at", "status", "booked_at"),
        # Goal 8: "bookings made today".
        Index("ix_bookings_booked_at", "booked_at"),
        Index("ix_bookings_member", "member_id"),
        # The partial unique index enforcing one active booking per member per
        # session is added in the migration — SQLAlchemy cannot express the
        # `WHERE status IN (...)` predicate against an enum here. It is also what
        # makes a double-submitted booking a clean 409 rather than a duplicate.
    )

    @property
    def is_active(self) -> bool:
        return self.status in BookingStatus.active()


class BookingEvent(Base):
    """One entry in a booking's timeline. Append-only, enforced by the database.

    Goal 9 says the timeline cannot be edited or deleted "including by studio
    staff", so the guarantee cannot rest on nobody writing an UPDATE later. The
    migration adds a BEFORE UPDATE OR DELETE row trigger, a BEFORE TRUNCATE
    statement trigger (row triggers do not fire on TRUNCATE), and revokes
    UPDATE/DELETE from the application role.
    """

    __tablename__ = "booking_events"

    # bigint identity rather than uuid, uniquely in this schema: an audit log wants
    # a strictly monotonic order with a deterministic tiebreak for two events in
    # the same microsecond. Ordering by a random uuid would be meaningless.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    event_type: Mapped[BookingEventType] = mapped_column(BOOKING_EVENT_TYPE)

    # Null for `created` and `note_added`; both populated for `status_changed`.
    old_status: Mapped[BookingStatus | None] = mapped_column(BOOKING_STATUS)
    new_status: Mapped[BookingStatus | None] = mapped_column(BOOKING_STATUS)

    note: Mapped[str | None] = mapped_column(Text)

    # Exactly one of these identifies the actor: a user, or the system. Automatic
    # waitlist promotions and the bulk cancellation behind a session delete have
    # no human actor, and recording the triggering staff member as though they
    # made each individual change would be a small lie in an audit log.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    occurred_at: Mapped[CreatedAt]

    booking: Mapped[Booking] = relationship(back_populates="events", lazy="raise_on_sql")
    actor: Mapped[User | None] = relationship(lazy="raise_on_sql")

    __table_args__ = (Index("ix_booking_events_booking", "booking_id", "id"),)
