"""Response shapes for the two operational reports."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class RoomUsageOut(BaseModel):
    """One room's share of a date range.

    ``minutes_booked`` rather than a percentage: a percentage needs opening hours,
    the studio has not told us what those are, and a figure computed against an
    invented denominator is worse than an honest raw number. The interface shows
    each room against the busiest one, which answers "which room is under-used"
    without anybody having to agree what 100% means.
    """

    room_id: uuid.UUID
    room_name: str
    sessions: int
    minutes_booked: int


class InstructorPayOut(BaseModel):
    """One instructor's teaching in a date range, and what it comes to.

    Both money fields are **minor units** — paise, pence, cents — and integers.
    Formatting them is the interface's job, and doing it here would mean deciding a
    currency this system has never been told.

    ``session_rate_minor`` and ``total_minor`` are null together, and null means "no
    rate has been set" rather than "nothing is owed".
    """

    instructor_id: uuid.UUID
    instructor_name: str
    sessions_taught: int
    minutes_taught: int
    session_rate_minor: int | None
    total_minor: int | None


class OperationsReport(BaseModel):
    """Both reports over the same window, in one response.

    One request rather than two, for the reason the dashboard gives: they are read
    side by side, and two round trips to a remote database to fill one screen is two
    chances for the halves to describe different moments.
    """

    starts: dt.date
    ends: dt.date
    rooms: list[RoomUsageOut]
    instructors: list[InstructorPayOut]

    # Null when any instructor who taught has no rate set, so the interface can say
    # the total is incomplete instead of printing a confident wrong number.
    payroll_total_minor: int | None
