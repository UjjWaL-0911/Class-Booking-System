"""Dashboard response shapes (goal 8)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel

from app.models.enums import BookingStatus


class HeadlineNumbers(BaseModel):
    """The four figures goal 8 asks for by name.

    Two of them are definitions rather than counts, and both are argued in
    schema.md: "no-shows this week" counts by the *session's* date rather than when
    it was settled, and "currently waitlisted" covers only sessions that have not
    yet started — otherwise it includes everyone ever waitlisted and only ever
    grows.
    """

    sessions_today: int
    bookings_today: int
    no_shows_this_week: int
    members_waitlisted: int


class StatusCount(BaseModel):
    status: BookingStatus
    count: int


class ClassCount(BaseModel):
    class_id: uuid.UUID
    class_title: str
    count: int


class WeekAttendance(BaseModel):
    """One bar of the eight-week chart."""

    week_start: dt.date
    attended: int
    no_show: int


class Dashboard(BaseModel):
    headline: HeadlineNumbers
    by_status: list[StatusCount]
    by_class: list[ClassCount]
    attendance_by_week: list[WeekAttendance]
    # Echoed back so a client is never left guessing which day the numbers are
    # "today" for — the studio's date, which is not always the viewer's.
    as_of: dt.date
    timezone: str
