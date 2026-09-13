"""Room utilisation and instructor payroll.

Two stretch ideas, one endpoint, because they are read on one screen over one date
range and answer two halves of the same question: what did the studio actually run
last month, and what did it cost.

Who sees what is two rules rather than one, because "what is this studio earning"
and "what am I owed" are different questions.

**Staff see both reports in full.** **An instructor sees one row — their own pay —
and no utilisation at all.** Withholding somebody's own pay from them would be an
odd thing for a system to do, and different in kind from letting them read what a
colleague earns. Utilisation is not theirs in either sense: it is a commercial
figure about the studio, and nothing an instructor needs to do their job.

The scoping lives in the query rather than here (`repositories/operations.py`), for
the same reason the session list does it — a filter that cannot be forgotten beats a
check that can. This router decides only whether to *ask* for utilisation.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query

from app.core.deps import Config, CurrentUser, DbSession, Now
from app.core.time import today as studio_today
from app.models.enums import UserRole
from app.repositories.operations import instructor_pay, room_utilisation
from app.schemas.operations import InstructorPayOut, OperationsReport, RoomUsageOut

router = APIRouter(prefix="/operations", tags=["operations"])

DEFAULT_DAYS_BACK = 30


@router.get("", response_model=OperationsReport, summary="Room use and instructor pay")
async def operations_report(
    db: DbSession,
    settings: Config,
    now: Now,
    viewer: CurrentUser,
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
) -> OperationsReport:
    """Both reports over one window. Defaults to the last thirty days.

    The window looks **backwards** by default, unlike every other date range in this
    API. Both of these are questions about what already happened — a room's
    utilisation next month is a statement about the timetable, not about the room,
    and nobody is paid in advance for a class they have not taught.

    An instructor gets their own pay row and an empty `rooms` list — not a 403. The
    response shape is the same for everybody, so the interface renders what it was
    given rather than branching on role in two places.
    """
    is_staff = viewer.role is UserRole.STAFF
    today = studio_today(settings.tz, now)
    starts = date_from or today - dt.timedelta(days=DEFAULT_DAYS_BACK)
    ends = date_to or today

    rooms = (
        await room_utilisation(db, viewer=viewer, tz=settings.tz, date_from=starts, date_to=ends)
        if is_staff
        else []
    )
    instructors = await instructor_pay(
        db, viewer=viewer, tz=settings.tz, date_from=starts, date_to=ends
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
