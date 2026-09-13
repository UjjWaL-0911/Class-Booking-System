"""Room utilisation and instructor payroll.

Two stretch ideas, one endpoint, because they are read on one screen over one date
range and answer two halves of the same question: what did the studio actually run
last month, and what did it cost.

Staff only. Utilisation is commercially sensitive and payroll is more so — an
instructor should not be able to read what a colleague is paid, and the visibility
filter would not stop that on its own, because the rows are grouped by *instructor*
rather than by session.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query

from app.core.deps import Config, DbSession, Now, StaffUser
from app.core.time import today as studio_today
from app.repositories.operations import instructor_pay, room_utilisation
from app.schemas.operations import InstructorPayOut, OperationsReport, RoomUsageOut

router = APIRouter(prefix="/operations", tags=["operations"])

DEFAULT_DAYS_BACK = 30


@router.get("", response_model=OperationsReport, summary="Room use and instructor pay")
async def operations_report(
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
) -> OperationsReport:
    """Both reports over one window. Defaults to the last thirty days.

    The window looks **backwards** by default, unlike every other date range in this
    API. Both of these are questions about what already happened — a room's
    utilisation next month is a statement about the timetable, not about the room,
    and nobody is paid in advance for a class they have not taught.
    """
    today = studio_today(settings.tz, now)
    starts = date_from or today - dt.timedelta(days=DEFAULT_DAYS_BACK)
    ends = date_to or today

    rooms = await room_utilisation(
        db, viewer=staff, tz=settings.tz, date_from=starts, date_to=ends
    )
    instructors = await instructor_pay(
        db, viewer=staff, tz=settings.tz, date_from=starts, date_to=ends
    )

    # Null if anybody who taught has no rate. A payroll total that quietly omits two
    # instructors is worse than no total, because it looks like an answer.
    totals = [row.total_minor for row in instructors]
    payroll_total = None if any(t is None for t in totals) else sum(t or 0 for t in totals)

    return OperationsReport(
        starts=starts,
        ends=ends,
        rooms=[RoomUsageOut(**row._asdict()) for row in rooms],
        instructors=[InstructorPayOut(**row._asdict()) for row in instructors],
        payroll_total_minor=payroll_total,
    )
