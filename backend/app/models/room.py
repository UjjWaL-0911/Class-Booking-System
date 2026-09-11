"""Bookable spaces."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.columns import CreatedAt, Str, UuidPk


class Room(Base):
    """A room a session can be scheduled in.

    A table rather than a text column on ``sessions`` for one concrete reason:
    overlap detection joins on ``room_id``, and a free-text label would let
    "Studio A" and "studio a" become two rooms that can be double-booked against
    each other. Seeded at deploy; not a managed feature in the interface.
    """

    __tablename__ = "rooms"

    id: Mapped[UuidPk]
    name: Mapped[Str] = mapped_column(unique=True)
    created_at: Mapped[CreatedAt]
