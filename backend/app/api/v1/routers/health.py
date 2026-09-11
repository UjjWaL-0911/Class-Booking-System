"""Health endpoints.

Two of them, and the distinction is operational rather than stylistic:

* ``/health`` is liveness only, with no database access. Render polls this
  frequently and it must stay cheap.
* ``/health/ready`` executes ``SELECT 1``. This is what the keep-warm cron hits,
  because a request that never touches Postgres would keep Render awake while
  doing nothing about Supabase's one-week inactivity pause — and a paused Supabase
  project needs a *manual* unpause, which turns the live URL into errors rather
  than a slow load.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness — no database access")
async def health() -> dict[str, str]:
    settings: Settings = get_settings()
    return {"status": "ok", "environment": settings.environment.value}


@router.get("/health/ready", summary="Readiness — reaches the database")
async def health_ready(db: DbSession, response: Response) -> dict[str, Any]:
    """Report 503 when the database is unreachable.

    Returning 200 with a failure noted in the body would let a broken deployment
    pass a platform health check, which is the opposite of the point.
    """
    settings: Settings = get_settings()
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # any failure to reach the database means not ready
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unavailable",
            "database": "unreachable",
            "detail": type(exc).__name__,
        }

    return {
        "status": "ok",
        "database": "reachable",
        "timezone": settings.studio_timezone,
    }
