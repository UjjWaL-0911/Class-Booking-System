"""Health endpoints.

Two of them, and the distinction is operational rather than stylistic:

* ``/health`` is liveness only, with no database access. Render polls this
  frequently and it must stay cheap.
* ``/health/ready`` executes ``SELECT 1``. This is what the keep-warm monitor hits,
  because a request that never touches Postgres would keep Render awake while
  doing nothing about Supabase's one-week inactivity pause — and a paused Supabase
  project needs a *manual* unpause, which turns the live URL into errors rather
  than a slow load.

**Both answer HEAD as well as GET, and that is not decoration.** Starlette adds
HEAD to any GET route automatically; FastAPI's ``APIRoute`` overrides that and
registers only what it is given. So a plain ``@router.get`` here returns **405** to
a HEAD probe — the path matches, the method does not — and an uptime monitor reads
that as the service being down while it is serving perfectly.

That is not hypothetical: it is exactly what happened when this was first
monitored. Free uptime checks default to HEAD because it is cheaper, and so do
plenty of load balancers and reverse proxies. A health endpoint that refuses the
most common probe method is a trap set for whoever points the next one at it.

HEAD costs nothing extra: Starlette strips the body from the response, so the
status is identical and no content is sent. ``/health/ready`` still runs its
``SELECT 1``, which is the point — the probe that reports liveness is also the one
that keeps the database's pause timer reset.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.deps import DbSession

router = APIRouter(tags=["health"])


@router.api_route("/health", methods=["GET", "HEAD"], summary="Liveness — no database access")
async def health() -> dict[str, str]:
    settings: Settings = get_settings()
    return {"status": "ok", "environment": settings.environment.value}


@router.api_route(
    "/health/ready", methods=["GET", "HEAD"], summary="Readiness — reaches the database"
)
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
