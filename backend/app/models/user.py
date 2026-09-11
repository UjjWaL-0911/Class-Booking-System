"""Staff and instructor accounts, and refresh-token state.

Members are deliberately *not* here: they are customer records with no login, in
``member.py``. Keeping the two apart is what makes the self-service phase an
additive change — ``members`` grows auth columns and ``bookings.member_id`` never
moves. See docs/architecture.md.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.columns import CreatedAt, Email, Str, UuidPk
from app.models.enums import USER_ROLE, UserRole

if TYPE_CHECKING:
    from app.models.class_session import ClassSession


class User(Base, TimestampMixin):
    """A person who can sign in: studio staff or an instructor."""

    __tablename__ = "users"

    id: Mapped[UuidPk]
    email: Mapped[Email] = mapped_column(unique=True)
    password_hash: Mapped[Str]
    full_name: Mapped[Str]
    role: Mapped[UserRole] = mapped_column(USER_ROLE)

    # Accounts are deactivated, never deleted: an instructor who leaves the studio
    # still has sessions and booking history that must stay intact. Every FK
    # pointing here is ON DELETE RESTRICT for the same reason.
    #
    # get_current_user loads this row on every authenticated request, so clearing
    # this flag revokes access immediately even though the access token is
    # stateless. That is the trade named in architecture.md: a round-trip per
    # request, in exchange for instant revocation.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    primary_sessions: Mapped[list[ClassSession]] = relationship(
        back_populates="primary_instructor",
        foreign_keys="ClassSession.primary_instructor_id",
        lazy="raise_on_sql",
    )

    @property
    def is_staff(self) -> bool:
        return self.role is UserRole.STAFF


class RefreshToken(Base):
    """One issued refresh token.

    Rotation and revocation are not properties a stateless token can have, which is
    the whole reason this table exists. The token itself is an opaque random string
    rather than a JWT — its only job is to be looked up — and only its SHA-256 hash
    is stored, so a database leak yields nothing usable.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[UuidPk]

    # CASCADE, unlike every other FK to users: these rows are session state, not
    # history, and deleting a user should not be blocked by them.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # One login lineage. Reuse detection revokes the whole family in one statement,
    # which is the only reason this column exists.
    family_id: Mapped[uuid.UUID]

    token_hash: Mapped[Str] = mapped_column(unique=True)
    issued_at: Mapped[CreatedAt]
    expires_at: Mapped[dt.datetime]
    revoked_at: Mapped[dt.datetime | None]

    # SET NULL, not the NO ACTION default: pruning expired rows would otherwise
    # raise a foreign-key violation as soon as a surviving row pointed at a pruned
    # predecessor — the normal case for any active session.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )

    user_agent: Mapped[str | None] = mapped_column(Text)

    # The client's address, parsed from X-Forwarded-For. request.client.host is
    # always the static-site proxy, so storing that would record nothing useful.
    client_ip: Mapped[str | None] = mapped_column(INET)

    user: Mapped[User] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        Index("ix_refresh_tokens_family", "family_id"),
        Index(
            "ix_refresh_tokens_active_user",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_refresh_tokens_expiry", "expires_at"),
    )

    def is_usable(self, now: dt.datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now
