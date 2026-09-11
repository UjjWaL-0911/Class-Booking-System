"""The dashboard aggregate (goal 8).

One query, not six. Two reasons:

* Every figure comes from the same snapshot, so the headline numbers cannot
  disagree with the breakdowns beside them — which they can if each is a separate
  round trip and a booking is created between two of them.
* A single ``AsyncSession`` cannot run queries concurrently; asyncpg raises
  ``InterfaceError: another operation is in progress``. So the alternative to one
  query is six *sequential* round trips to a remote database, not six parallel
  ones. "Async" does not mean "concurrent on a resource that is serial".

Written as SQL rather than assembled through the ORM. This is a reporting query
with CTEs, ``FILTER`` clauses and a generated week series; expressing that in
SQLAlchemy would obscure it rather than protect anything, and every value
interpolated below is either a bound parameter or a boolean the caller controls.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import today as studio_today
from app.core.time import week_bounds
from app.models.enums import UserRole
from app.models.user import User

WEEKS_CHARTED = 8


class DashboardData(NamedTuple):
    headline: dict[str, int]
    by_status: list[dict[str, Any]]
    by_class: list[dict[str, Any]]
    attendance_by_week: list[dict[str, Any]]
    as_of: dt.date


_QUERY = """
WITH scope AS (
    -- Every session this viewer may see, with its local date resolved once.
    SELECT s.id,
           s.starts_at,
           s.class_id,
           (s.starts_at AT TIME ZONE :tz)::date AS local_date
    FROM sessions s
    -- The visibility rule from goal 1, inline rather than composed in: staff see
    -- everything, an instructor sees the sessions they lead or co-instruct, so
    -- their dashboard describes their own teaching rather than the whole studio.
    -- Written here as a literal so this module builds no SQL by string
    -- concatenation at all.
    WHERE s.deleted_at IS NULL
      AND (
          :is_staff
          OR s.primary_instructor_id = :viewer_id
          OR EXISTS (
              SELECT 1 FROM session_co_instructors ci
              WHERE ci.session_id = s.id AND ci.user_id = :viewer_id
          )
      )
),
b AS (
    -- Bookings on those sessions, carrying the session's date down so every
    -- figure below can be bucketed without joining again.
    SELECT bk.id,
           bk.status,
           bk.booked_at,
           bk.member_id,
           sc.class_id,
           sc.starts_at,
           sc.local_date
    FROM bookings bk
    JOIN scope sc ON sc.id = bk.session_id
),
weeks AS (
    -- Generated rather than derived from the data, so a week with no classes is
    -- a zero bar instead of a gap in the chart.
    -- CAST(...) rather than :week_start::timestamp. SQLAlchemy's text() will not
    -- recognise a bind parameter immediately followed by '::' — its regex has a
    -- negative lookahead for a colon — so the postfix form passes straight through
    -- to PostgreSQL as a literal ':week_start' and fails at parse time.
    SELECT generate_series(
        date_trunc('week', CAST(:week_start AS timestamp))
            - make_interval(weeks => :weeks - 1),
        date_trunc('week', CAST(:week_start AS timestamp)),
        '1 week'
    )::date AS week_start
)
SELECT
    (SELECT count(*) FROM scope WHERE local_date = :today) AS sessions_today,

    (SELECT count(*) FROM b
      WHERE (booked_at AT TIME ZONE :tz)::date = :today) AS bookings_today,

    -- By the session's date, not when it was settled: staff think in terms of the
    -- classes that happened this week, and settlement may be recorded days later.
    (SELECT count(*) FROM b
      WHERE status = 'no_show'
        AND local_date BETWEEN :week_start AND :week_end) AS no_shows_this_week,

    -- Future sessions only. Nothing closes out a waitlist entry when its session
    -- passes, so an unscoped count would include everyone ever waitlisted and
    -- could only ever grow.
    (SELECT count(DISTINCT member_id) FROM b
      WHERE status = 'waitlisted' AND starts_at > now()) AS members_waitlisted,

    (SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
        SELECT status::text AS status, count(*) AS count
        FROM b GROUP BY status ORDER BY status
    ) t) AS by_status,

    (SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
        SELECT c.id::text AS class_id, c.title AS class_title, count(*) AS count
        FROM b JOIN classes c ON c.id = b.class_id
        GROUP BY c.id, c.title
        ORDER BY count(*) DESC, c.title
    ) t) AS by_class,

    (SELECT coalesce(json_agg(row_to_json(t) ORDER BY t.week_start), '[]'::json) FROM (
        SELECT w.week_start,
               count(*) FILTER (WHERE b.status = 'attended') AS attended,
               count(*) FILTER (WHERE b.status = 'no_show')  AS no_show
        FROM weeks w
        LEFT JOIN b ON date_trunc('week', b.local_date::timestamp)::date = w.week_start
        GROUP BY w.week_start
    ) t) AS attendance_by_week
"""


async def load_dashboard(
    db: AsyncSession,
    *,
    viewer: User,
    tz_name: str,
    now: dt.datetime,
) -> DashboardData:
    tz = ZoneInfo(tz_name)
    today = studio_today(tz, now)
    week_start, week_end = week_bounds(today)

    row = (
        await db.execute(
            text(_QUERY),
            {
                "is_staff": viewer.role is UserRole.STAFF,
                "viewer_id": viewer.id,
                "tz": tz_name,
                "today": today,
                "week_start": week_start,
                "week_end": week_end,
                "weeks": WEEKS_CHARTED,
            },
        )
    ).one()

    return DashboardData(
        headline={
            "sessions_today": row.sessions_today,
            "bookings_today": row.bookings_today,
            "no_shows_this_week": row.no_shows_this_week,
            "members_waitlisted": row.members_waitlisted,
        },
        by_status=list(row.by_status),
        by_class=list(row.by_class),
        attendance_by_week=list(row.attendance_by_week),
        as_of=today,
    )
