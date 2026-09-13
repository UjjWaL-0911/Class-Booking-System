"""The shapes the staff-only ``/users`` endpoints use.

Separate from ``schemas/auth.py`` on purpose. ``UserOut`` lives there and is
returned by **sign-in**, so every field added to it reaches every account on every
login. A pay rate is not something the sign-in response should be carrying, and
"remember not to widen that model" is not a safeguard — it is a thing to forget.

So the rate hangs off a subclass that only the staff-only list returns. The same
structural argument the public timetable makes: the shape that must not leak is a
shape that does not contain the field at all.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.auth import UserOut

# The column is a 32-bit integer, so the ceiling is the column's rather than a
# policy I invented. Its job is to turn a slipped decimal point into a 422 that
# says what is wrong, instead of an overflow the driver reports as a 500.
MAX_RATE_MINOR = 2_147_483_647


class TeacherOut(UserOut):
    """A colleague, plus what they are paid to lead one session.

    **Minor units, integer, no currency.** Paise, pence, cents — the same
    representation the payroll report uses, and for the same reason: money in a
    float is a rounding error waiting for a year-end total. Which currency it is
    in, this system has never been told; the interface prints the number bare
    rather than inventing a symbol for it.

    Null means **no rate has been set**, which is not zero. One is a thing
    somebody has to go and decide; the other is a decision. The payroll report
    already refuses to add them together, and this list says "Not set" rather
    than printing 0.00 for the same reason.
    """

    session_rate_minor: int | None


class UserUpdate(BaseModel):
    """What may be changed about a colleague: the rate, and nothing else.

    The field is **required**, unusually for a PATCH body, and that is the point.
    A partial-update schema always has to answer "is an absent field a no-op or an
    instruction to clear it?", and with one editable field whose null is
    meaningful, requiring it removes the question: sending a number sets the rate,
    sending null clears it, and there is no third case. When a second editable
    field arrives, that is the day ``exclude_unset`` starts earning its keep.

    Name, email and role are deliberately not here. Each is a real feature with
    rules of its own — an email change is an identity change, a role change is an
    authorisation change — and a dialog whose fields half-work is worse than one
    that is honest about what it edits.
    """

    session_rate_minor: int | None = Field(ge=0, le=MAX_RATE_MINOR)
