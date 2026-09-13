"""What the public is allowed to see of the timetable.

A separate response model, not a filtered `SessionOut`. That is the whole point of
the file: `SessionOut` carries the instructor's email, the room id, the session's
`version` and four booking counts, and every one of those is a field somebody could
later add to a shape that is also served to anyone on the internet.

The rule this follows is the same one that keeps `password_hash` out of `UserOut` —
a field that does not exist in the output model cannot leak from it, however the
endpoint is edited later. Deriving this shape from `SessionOut` would put the two
audiences one careless inheritance away from each other.

What is exposed is what a poster on the studio door would say: what the class is,
when, how long, who is teaching, and whether there is room. Notably absent: any
member, any booking, any id that can be used against the authenticated API, and the
instructor's email address.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class PublicSession(BaseModel):
    """One class, as a stranger sees it."""

    session_date: dt.date
    start_time: dt.time
    duration_min: int

    class_title: str
    discipline: str
    description: str

    # The instructor's name, because a studio advertises who is teaching. Not their
    # id and not their email: the first is only useful against endpoints this
    # caller cannot reach, and the second is personal data with no public purpose.
    instructor_name: str
    room_name: str

    # "Is there room" rather than "how many are booked". A remaining count is what a
    # prospective member needs; the booked count is an operational figure, and
    # publishing it tells the internet how the studio's business is going.
    spots_remaining: int
    is_full: bool


class PublicSchedule(BaseModel):
    """A window of upcoming classes, plus the dates it covers.

    The bounds are returned rather than assumed by the caller: this endpoint decides
    how far ahead it will look, and a page that prints "next two weeks" should be
    printing the server's answer rather than its own guess.
    """

    days_ahead: int
    starts: dt.date
    ends: dt.date

    # True when the cap cut the list short. Without it the response states a window
    # it did not actually deliver, and a studio busy enough to hit the cap is
    # exactly the one that would never notice the tail going missing.
    truncated: bool

    sessions: list[PublicSession]
