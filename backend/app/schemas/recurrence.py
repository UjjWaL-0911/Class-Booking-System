"""Recurring session generation (goal 7)."""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.schemas.class_session import SessionOut


class SkipReason(StrEnum):
    """Why one occurrence was not created.

    Goal 7 names the first two; the third is what happens when the clocks change,
    and it is reported rather than silently shifted.
    """

    ROOM_BUSY = "room_busy"
    INSTRUCTOR_BUSY = "instructor_busy"
    NONEXISTENT_LOCAL_TIME = "nonexistent_local_time"


class RecurrenceCreate(BaseModel):
    """A weekly pattern: the same class, instructor, room and start time, repeated.

    ``weekdays`` uses Python's convention — Monday is 0 — so a Monday/Wednesday
    class is ``[0, 2]``.
    """

    class_id: uuid.UUID
    primary_instructor_id: uuid.UUID
    room_id: uuid.UUID
    start_time: dt.time
    weekdays: list[int] = Field(min_length=1, max_length=7)
    date_from: dt.date
    date_to: dt.date
    duration_min: int | None = Field(default=None, gt=0, le=600)
    capacity: int | None = Field(default=None, gt=0, le=1000)

    @model_validator(mode="after")
    def _check(self) -> RecurrenceCreate:
        if self.date_to < self.date_from:
            raise ValueError("date_to must not be before date_from")
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("weekdays must be between 0 (Monday) and 6 (Sunday)")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays must not repeat")
        return self


class SkippedOccurrence(BaseModel):
    """One occurrence that was not created, and why.

    The conflicting session is named where there is one: "skipped" without saying
    what it collided with leaves staff to hunt through the schedule themselves.
    """

    session_date: dt.date
    start_time: dt.time
    reason: SkipReason
    detail: str
    conflicting_session_id: uuid.UUID | None = None


class GenerationReport(BaseModel):
    """Goal 7: "The result reports which sessions were created and which were
    skipped because the chosen instructor or room was already booked in an
    overlapping window."
    """

    requested: int
    created: list[SessionOut]
    skipped: list[SkippedOccurrence]
