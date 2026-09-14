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

from pydantic import BaseModel

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
