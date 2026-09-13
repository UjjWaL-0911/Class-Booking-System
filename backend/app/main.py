"""FastAPI application factory.

Deliberately thin: it wires configuration, lifespan, middleware, exception handlers
and routers together and does nothing else. Business logic lives in ``app/services``,
HTTP concerns in ``app/api``.

There is no CORS middleware. The SPA's static host rewrites ``/api/*`` to this
service, so the browser only ever sees one origin — which is also what makes the
refresh cookie first-party. See docs/architecture.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.routers import (
    alerts,
    auth,
    bookings,
    classes,
    dashboard,
    exports,
    health,
    members,
    public_schedule,
    rooms,
    sessions,
    users,
)
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, request_context_middleware
from app.db.engine import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the connection pool's lifetime.

    The engine is created lazily on first use rather than here, so the process can
    start and report liveness even when the database is briefly unreachable —
    which matters on a free tier where a wake-from-sleep and a cold database can
    coincide. Disposal, though, must be explicit: without it, pooled connections
    are left open on the server when the instance is recycled.
    """
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Class Booking System",
        description="Studio scheduling, membership and booking management.",
        version="0.1.0",
        docs_url=settings.docs_url,
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    # Registered first, so it is outermost: every other layer's work — including
    # an exception handler's response — happens inside a bound request id.
    app.middleware("http")(request_context_middleware)

    register_exception_handlers(app)

    # Health lives at the root, outside the versioned prefix: it is infrastructure,
    # not part of the public API contract, and platform probes should not have to
    # know about API versions.
    app.include_router(health.router)

    for versioned in (
        auth.router,
        classes.router,
        # Unauthenticated, and mounted alongside the rest on purpose: it is part of
        # the API contract rather than infrastructure, so it carries the version
        # prefix like everything else. What makes it public is the absence of a
        # user dependency inside it, which is visible in one file.
        public_schedule.router,
        rooms.router,
        users.router,
        members.router,
        sessions.router,
        bookings.router,
        exports.router,
        dashboard.router,
        alerts.router,
    ):
        app.include_router(versioned, prefix=settings.api_v1_prefix)

    return app


app = create_app()
