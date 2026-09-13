"""Query and result shapes for the bookings list (goal 6)."""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.models.enums import BookingStatus


class BookingSort(StrEnum):
    """The three orderings goal 6 asks for.

    ``SESSION`` sorts by the session's start time rather than its id — "sorting by
    session" means chronologically to anyone reading a schedule.
    """

    BOOKED_AT = "booked_at"
    STATUS = "status"
    SESSION = "session"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class BookingListItem(BaseModel):
    """One row of the list.

    Flattened deliberately: the list shows member, class and session together, and
    nesting three objects per row would make the client reassemble what the query
    already joined.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: BookingStatus
    booked_at: dt.datetime

    member_id: uuid.UUID
    member_name: str
    member_email: str

    session_id: uuid.UUID
    session_starts_at: dt.datetime
    session_date: dt.date
    session_start_time: dt.time

    class_id: uuid.UUID
    class_title: str
    # Carried so the list can speak the studio's language rather than a generic
    # one: a cancelled place on a yoga class frees a mat, not a "spot". The join
    # is already here for the title, so this costs nothing but the column.
    discipline: str

    # A waitlisted booking on a session that has already happened is displayed as
    # such rather than silently rewritten — see "Two query definitions that are
    # decisions" in schema.md.
    session_has_passed: bool

    # 1-based place in the queue, and null unless this booking is waitlisted.
    # Members have no accounts here, so "waitlist position visibility" means the
    # person at the desk can answer "where am I?" without opening the session.
    waitlist_position: int | None = None
