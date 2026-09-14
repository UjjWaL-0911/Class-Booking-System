"""What a signed-in member may see about themselves.

Written from scratch, not derived from ``BookingListItem`` or ``MemberOut``, for
the reason ``PublicSession`` exists: those shapes are built for the people who run
the studio. ``BookingListItem`` carries another member's id, name and email on
every row, because the desk's list is *about* who booked. Reuse it here filtered
to one member and every field added to it later reaches a customer unless somebody
remembers to filter that one too — and the remembering would have to happen in a
different file from the adding.

A model that never had the field cannot leak it. So this file names exactly what a
member is told about their own booking, and the tests assert the key set rather
than the absence of particular fields: widening it is a failing test rather than a
quiet disclosure.

Notably absent: any other member, any booking count, the session's ``version``,
the instructor's email, and every id except the booking's own — which exists
because cancelling needs a handle, and is the only id a member can act on.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.models.enums import BookingStatus


class MyBooking(BaseModel):
    """One of the member's own bookings."""

    id: uuid.UUID
    status: BookingStatus
    booked_at: dt.datetime

    session_date: dt.date
    start_time: dt.time
    duration_min: int

    class_title: str
    discipline: str
    instructor_name: str
    room_name: str

    # A waitlisted booking on a session that has already happened stays waitlisted
    # rather than being silently rewritten, so the interface needs to know which
    # it is looking at. Same decision the desk's list makes.
    session_has_passed: bool

    # 1-based place in the queue, null unless waitlisted. Counted with the same
    # ordering the promotion query uses, so what a member is told matches who
    # actually gets the next free seat.
    waitlist_position: int | None = None

    # Whether *this member* may still cancel it. Derived on the server rather than
    # inferred in the interface from status and date, because the rule belongs
    # where it is enforced and a button that appears when the API would refuse is
    # worse than no button.
    can_cancel: bool = False


class MyMembership(BaseModel):
    """Who the member is, and whether they may book today.

    ``is_expired`` is computed in the studio's timezone rather than left to the
    browser: a membership is valid *through* its expiry date, and "today" in
    Kolkata is not "today" wherever the phone happens to be.

    This is also the honest answer to "why can I not book?". Enabling a login does
    not grant a membership — goal 4's expiry rule still decides — so a member whose
    membership has lapsed can sign in, read this, and understand the refusal before
    they meet it.
    """

    full_name: str
    email: str
    membership_expiry: dt.date
    is_expired: bool


class BookableSession(BaseModel):
    """One upcoming class, as the member choosing between them sees it.

    Close to ``PublicSession`` but not the same model, and the difference is the
    point: this one carries ``id``. The public timetable deliberately has none —
    "no id that can be used against the authenticated API" — because a stranger
    has nothing to do with one. A member does: naming a session is how they book
    it. Two audiences, two shapes, neither filtered from the other.

    ``my_status`` is the field that makes this worth its own endpoint. Without it
    the interface would have to cross-reference the member's bookings against the
    timetable in the browser and decide what the button says, which is a rule
    living in the wrong place and drifting the first time a status is added.
    """

    id: uuid.UUID

    session_date: dt.date
    start_time: dt.time
    duration_min: int

    class_title: str
    discipline: str
    description: str
    instructor_name: str
    room_name: str

    spots_remaining: int
    is_full: bool

    # This member's own active booking on this session — `booked`, `waitlisted`,
    # or null if they have none. Cancelled and settled bookings do not count: the
    # question the interface is asking is "may I book this", and only an active
    # booking answers no.
    my_status: BookingStatus | None = None

    # Where they are in the queue, when they are in it. Carried here as well as on
    # `MyBooking` because a member looking at the timetable and a member looking at
    # their own list are asking the same question — "where am I?" — and the first
    # screen answering "you are on the waiting list" without the number is a worse
    # answer than the second gives, for no reason a reader could guess.
    my_waitlist_position: int | None = None


class MyBookingCreate(BaseModel):
    """Book myself onto a session.

    **One field, and the absence of the other is the security model.** The staff
    endpoint takes a ``member_id`` because the desk books on behalf of whoever is
    standing at it. Here the member is the caller, resolved from the credential —
    so there is no id to supply, and therefore none to tamper with.
    """

    session_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)


class MyCancellation(BaseModel):
    """Calling off my own booking. The note is optional and is mine to write."""

    note: str | None = Field(default=None, max_length=1000)
