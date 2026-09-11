"""Dashboard endpoint (goal 8)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import Config, CurrentUser, DbSession, Now
from app.repositories.dashboard import load_dashboard
from app.schemas.dashboard import (
    ClassCount,
    Dashboard,
    HeadlineNumbers,
    StatusCount,
    WeekAttendance,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard, summary="Headline numbers and breakdowns")
async def get_dashboard(
    db: DbSession, viewer: CurrentUser, settings: Config, now: Now
) -> Dashboard:
    """Everything goal 8 asks for, from one query.

    Scoped to what the viewer can see, so an instructor's dashboard describes
    their own teaching rather than the whole studio. Dates are bucketed in the
    studio's timezone — "today" means the studio's today, which is not always the
    viewer's.
    """
    data = await load_dashboard(db, viewer=viewer, tz_name=settings.studio_timezone, now=now)
    return Dashboard(
        headline=HeadlineNumbers(**data.headline),
        by_status=[StatusCount(**row) for row in data.by_status],
        by_class=[ClassCount(**row) for row in data.by_class],
        attendance_by_week=[WeekAttendance(**row) for row in data.attendance_by_week],
        as_of=data.as_of,
        timezone=settings.studio_timezone,
    )
