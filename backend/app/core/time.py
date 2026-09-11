"""Studio-local time.

Sessions are scheduled in wall-clock terms — "Tuesday at 18:00" — and stored as
UTC instants. Every conversion between the two goes through this module, because
getting it wrong is silent: the class simply happens at the wrong time for part of
the year, and nothing raises.

The rule: a wall-clock time is only meaningful with a timezone attached, so no
function here accepts a naive datetime without also being told which zone it is in.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


class NonexistentLocalTime(ValueError):
    """A wall-clock time that does not exist on that date.

    Spring-forward skips an hour. A studio scheduling an 02:30 class on that date
    has asked for a time that never occurs, and silently shifting it would be worse
    than refusing — so the recurring generator reports the occurrence as skipped
    with this reason rather than inventing one.
    """


def to_utc(day: dt.date, at: dt.time, tz: ZoneInfo) -> dt.datetime:
    """Combine a local date and time into a UTC instant.

    Two edge cases, both real once a year:

    * **Spring forward** removes an hour, so some wall-clock times do not exist.
      Python happily produces a datetime anyway, so it is detected explicitly by
      round-tripping through UTC and checking the local time survived.
    * **Fall back** repeats an hour, so some wall-clock times happen twice. The
      first (pre-transition) occurrence is chosen, which is what ``fold=0`` means
      and what a person reading a schedule would assume.
    """
    local = dt.datetime.combine(day, at, tzinfo=tz)

    # A nonexistent time normalises to a different wall clock when converted out
    # and back. An existing time round-trips unchanged.
    round_tripped = local.astimezone(dt.UTC).astimezone(tz)
    if (round_tripped.date(), round_tripped.time()) != (day, at):
        raise NonexistentLocalTime(
            f"{day.isoformat()} {at.isoformat()} does not exist in {tz.key} "
            f"(the clocks change that day)."
        )

    return local.astimezone(dt.UTC)


def to_local(instant: dt.datetime, tz: ZoneInfo) -> dt.datetime:
    """Render a stored instant in the studio's timezone."""
    return instant.astimezone(tz)


def local_date(instant: dt.datetime, tz: ZoneInfo) -> dt.date:
    """The studio-local calendar date of an instant.

    This is what "sessions today" and "no-shows this week" count by. Using the
    UTC date instead would put an evening class in Kolkata on the wrong day.
    """
    return instant.astimezone(tz).date()


def today(tz: ZoneInfo, now: dt.datetime | None = None) -> dt.date:
    """The studio's current date, which is not always the server's."""
    return (now or dt.datetime.now(dt.UTC)).astimezone(tz).date()


def week_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    """The Monday-to-Sunday week containing ``day``, inclusive.

    Monday because that is how a class schedule reads; the alternative would be a
    configuration option nobody asked for.
    """
    monday = day - dt.timedelta(days=day.weekday())
    return monday, monday + dt.timedelta(days=6)
