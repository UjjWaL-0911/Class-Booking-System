"""Booking one member into a whole term of a class.

The shape deliberately mirrors ``recurrence.py``. That file reports which *sessions*
were created and which were skipped; this one reports which *bookings* were taken
and which were skipped, for the same reason — a bulk action that silently does
fourteen things is a bulk action nobody can check.

The difference worth noticing is that this report has three outcomes rather than
two. A session being full is not a failure here: the member goes on the waiting
list, which is what goal 4 says should happen, so "waitlisted" is a result rather
than a skip.
"""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class BookingSkipReason(StrEnum):
    """Why one session in the term did not produce a booking.

    Every one of these is a rule the single-booking path already enforces. They are
    named here so the report can say which rule applied rather than returning a
    sentence the interface would have to parse.
    """

    ALREADY_BOOKED = "already_booked"
    MEMBERSHIP_EXPIRED = "membership_expired"
    SESSION_STARTED = "session_started"
    CLASS_ARCHIVED = "class_archived"
    REFUSED = "refused"


class TermBookingCreate(BaseModel):
    """Book one member into every session of a class across a date range.

    ``weekdays`` is optional and filters the sessions that already exist — it does
    not create any. A member joining a Monday/Wednesday class mid-term wants the
    Mondays and Wednesdays that are already on the timetable, and ``[0, 2]`` says
    so. Omitted means every session of that class in the window.
    """

    member_id: uuid.UUID
    class_id: uuid.UUID
    date_from: dt.date
    date_to: dt.date
    weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _check(self) -> TermBookingCreate:
        if self.date_to < self.date_from:
            raise ValueError("date_to must not be before date_from")
        if self.weekdays is not None:
            if any(d < 0 or d > 6 for d in self.weekdays):
                raise ValueError("weekdays must be between 0 (Monday) and 6 (Sunday)")
            if len(set(self.weekdays)) != len(self.weekdays):
                raise ValueError("weekdays must not repeat")
        return self


class TermBookingOutcome(BaseModel):
    """One session in the range, and what happened on it."""

    session_id: uuid.UUID
    session_date: dt.date
    start_time: dt.time

    booking_id: uuid.UUID | None = None
    waitlisted: bool = False

    reason: BookingSkipReason | None = None
    detail: str | None = None


class TermBookingReport(BaseModel):
    """What the bulk action did, session by session.

    ``booked`` and ``waitlisted`` are counted separately because they mean
    different things to the person at the desk: one is a place, the other is a
    queue, and a member is told a different sentence for each.
    """

    requested: int
    booked: list[TermBookingOutcome]
    waitlisted: list[TermBookingOutcome]
    skipped: list[TermBookingOutcome]
