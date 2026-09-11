"""Attendance export and schedule generation (goal 7).

Both hang off a session or a class rather than living under a generic ``/export``
namespace, because both are operations on a thing rather than a feature of their
own.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.core.deps import Config, CurrentUser, DbSession
from app.services.export_service import ExportService
from app.services.session_service import SessionService

router = APIRouter(tags=["exports"])


@router.get(
    "/sessions/{session_id}/attendance.csv",
    response_class=Response,
    summary="Export a session's attendance as CSV",
)
async def export_attendance(
    session_id: uuid.UUID,
    db: DbSession,
    settings: Config,
    viewer: CurrentUser,
) -> Response:
    """Every booking on the session with its member and final status.

    Scoped by the same visibility filter as everything else, so an instructor can
    export the register for a class they teach and nothing else — fetching another
    instructor's session returns 404 rather than 403, which is what the filter
    naturally produces and also what avoids confirming the session exists.
    """
    service = SessionService(db, settings)
    session = await service.get(session_id, viewer)

    body = await ExportService(db, settings.tz).attendance_csv(session)
    filename = ExportService.filename(session, session.studio_class.title, settings.tz)

    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
