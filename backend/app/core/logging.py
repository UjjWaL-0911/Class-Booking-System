"""Structured logging and request correlation.

Two jobs:

* **Make logs machine-readable in production.** Render captures stdout, and a line
  you can filter and aggregate is worth far more than a pretty one. Locally the
  same events render as readable console output, because a developer reading JSON
  in a terminal is a small tax paid on every run.

* **Correlate everything in a request.** A request id is generated at the edge,
  bound to a context variable, attached to every log line emitted while handling
  that request, and returned in the response header. When somebody reports "I got
  a 503 at 14:32", that header is what turns it into a single greppable trace.

The request id is bound with ``structlog.contextvars`` rather than passed around,
because the alternative is threading a logger through every service signature —
and a log call that has to be given context is a log call that will eventually be
written without it.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Environment, Settings

REQUEST_ID_HEADER = "X-Request-ID"

# Paths that would otherwise dominate the log. The keep-warm cron hits /health
# every ten minutes for the lifetime of the deployment, and Render polls it more
# often than that; none of it is worth a line unless it fails.
_QUIET_PATHS = frozenset({"/health", "/health/ready"})


def configure_logging(settings: Settings) -> None:
    """Set up structlog and route the standard library through it.

    Uvicorn and SQLAlchemy log through ``logging``, so without the last step here
    their output would bypass the processors entirely and arrive in a different
    shape from everything else.
    """
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.environment is Environment.PRODUCTION
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Hand the standard library the same formatting, so uvicorn's access lines and
    # SQLAlchemy's warnings do not arrive in a second, different format.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
            foreign_pre_chain=shared,
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # Uvicorn installs its own handlers; propagate to ours instead of duplicating.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Bind a request id for the duration of the request, and time it.

    The id is taken from the incoming header when one is present, so a trace
    started by a proxy or a client survives into our logs rather than being
    replaced by a fresh one.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    log = structlog.get_logger("api")
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Logged here as well as by the exception handlers, because a failure that
        # escapes those would otherwise leave no record tied to this request id.
        log.exception(
            "request_failed", duration_ms=round((time.perf_counter() - started) * 1000, 1)
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers[REQUEST_ID_HEADER] = request_id

    if request.url.path not in _QUIET_PATHS or response.status_code >= 400:
        log.info(
            "request_completed",
            status=response.status_code,
            duration_ms=duration_ms,
        )

    return response
