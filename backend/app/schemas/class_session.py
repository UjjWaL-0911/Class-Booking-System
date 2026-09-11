"""Session request and response bodies (goals 3 and 5).

Sessions are scheduled in wall-clock terms — a date and a start time in the
studio's timezone — and stored as UTC instants. The wire format is deliberately
the local pair, because that is what staff type and what the schedule shows;
converting at the boundary keeps the timezone question in one place.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    class_id: uuid.UUID
    session_date: dt.date
    start_time: dt.time
    primary_instructor_id: uuid.UUID
    room_id: uuid.UUID

    # Omit to inherit the class default. Goal 3 requires both to be overridable
    # per session, and None here means "inherit" rather than "no value".
    duration_min: int | None = Field(default=None, gt=0, le=600)
    capacity: int | None = Field(default=None, gt=0, le=1000)


class SessionUpdate(BaseModel):
    version: int
    session_date: dt.date | None = None
    start_time: dt.time | None = None
    primary_instructor_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    duration_min: int | None = Field(default=None, gt=0, le=600)
    capacity: int | None = Field(default=None, gt=0, le=1000)


class InstructorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    class_title: str
    discipline: str

    # Both representations are returned: the local pair is what a schedule
    # displays, the UTC instants are what a client should compare or sort on.
    session_date: dt.date
    start_time: dt.time
    starts_at: dt.datetime
    ends_at: dt.datetime

    room_id: uuid.UUID
    room_name: str
    primary_instructor: InstructorOut
    co_instructors: list[InstructorOut]

    duration_min: int
    capacity: int

    # ``booked_count`` counts *active* bookings, which is what capacity decisions
    # need and what "how full is it" means for a class that has not happened yet.
    # Once a class is over its bookings are settled, so booked_count falls to zero
    # and a client rendering only that would draw a full class as an empty room.
    # The settled counts are returned alongside so the same screen can say what
    # actually happened: attended + no_show + booked is how many people had a spot.
    booked_count: int
    waitlisted_count: int
    attended_count: int
    no_show_count: int
    seats_remaining: int

    version: int


class CoInstructorAdd(BaseModel):
    user_id: uuid.UUID
