"""Members — customer records — and membership alert dismissals.

Members have no authentication columns. They are records the studio keeps, not
accounts: goal 1 gives logins to staff and instructors only, and bookings are
created for a member by staff. The self-service phase adds ``password_hash`` and
``last_login_at`` here, and ``bookings.member_id`` never moves.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.columns import CalendarDate, CreatedAt, Email, Str, UuidPk

if TYPE_CHECKING:
    from app.models.booking import Booking


class Member(Base, TimestampMixin):
    """Someone who attends classes."""

    __tablename__ = "members"

    id: Mapped[UuidPk]
    full_name: Mapped[Str]

    # Unique: a returning customer keeps one record rather than accumulating
    # duplicates, which keeps their booking history and alert state in one place.
    email: Mapped[Email] = mapped_column(unique=True)

    # A calendar date, not an instant. Expired means `< current_date` in the
    # studio timezone, so a membership is still valid on its expiry date itself.
    membership_expiry: Mapped[CalendarDate]

    notes: Mapped[Str] = mapped_column(server_default="")

    bookings: Mapped[list[Booking]] = relationship(back_populates="member", lazy="raise_on_sql")

    __table_args__ = (
        # Goal 6 searches name and email. gin_trgm_ops indexes are added in the
        # migration: the email one must be built on (email::text), because the
        # planner ignores a trigram index for citext-native operators.
        Index("ix_members_expiry", "membership_expiry"),
    )

    def is_expired_on(self, today: dt.date) -> bool:
        return self.membership_expiry < today


class MembershipAlertDismissal(Base):
    """A staff member dismissing one member's expiry alert (goal 10).

    The design turns on which value is stored: the member's ``membership_expiry``
    *as it was when dismissed*. An alert is suppressed only when a dismissal row
    matches the member's **present** expiry — so setting a new later date leaves
    no match, and the alert reappears by itself once that date enters the
    seven-day window. The re-trigger requirement needs no background job and no
    per-member flag; it falls out of the key.

    A trigger additionally clears these rows whenever the expiry changes at all,
    which closes the one case value-matching misses: dismiss, extend the expiry,
    then correct it back to the original date.
    """

    __tablename__ = "membership_alert_dismissals"

    id: Mapped[UuidPk]

    # CASCADE: these are operational state, not audit data, so they may be deleted.
    # `booking_events` is the opposite and is never deleted from.
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"))
    dismissed_expiry: Mapped[CalendarDate]
    dismissed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    dismissed_at: Mapped[CreatedAt]

    member: Mapped[Member] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        UniqueConstraint("member_id", "dismissed_expiry", name="uq_dismissal_member_expiry"),
    )
