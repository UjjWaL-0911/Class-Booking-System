"""Booking request and response bodies (goals 4 and 9)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BookingEventType, BookingStatus


class BookingCreate(BaseModel):
    session_id: uuid.UUID
    member_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)


class BookingCancel(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class BookingSettle(BaseModel):
    """Goal 4: once the session's time has passed, a Booked booking is settled as
    Attended or No Show. Those are the only two outcomes, so this is an enum of
    exactly two rather than a free status field."""

    attended: bool
    note: str | None = Field(default=None, max_length=1000)


class NoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class MemberSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    membership_expiry: dt.date


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    status: BookingStatus
    booked_at: dt.datetime
    cancelled_at: dt.datetime | None
    settled_at: dt.datetime | None
    member: MemberSummary


class BookingEventOut(BaseModel):
    """One entry in the immutable timeline (goal 9).

    ``actor_name`` is null exactly when ``is_system`` is true — automatic
    promotions and the bulk cancellation behind a session delete have no human
    actor, and naming the staff member who triggered them would be a small lie.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: BookingEventType
    old_status: BookingStatus | None
    new_status: BookingStatus | None
    note: str | None
    actor_name: str | None
    is_system: bool
    occurred_at: dt.datetime


class BookingWithTimeline(BookingOut):
    events: list[BookingEventOut]


class CancelResult(BaseModel):
    """Cancelling can promote someone, so the response says whether it did.

    The caller needs to know: a freed seat that was immediately refilled looks
    identical to one that was not, from the session's seat count alone.
    """

    booking: BookingOut
    promoted: BookingOut | None = None
