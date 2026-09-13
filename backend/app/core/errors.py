"""Domain exceptions and their HTTP mapping.

Services raise these; one set of handlers turns them into responses. The rule that
keeps the layering honest is that a service never imports ``fastapi`` — it says what
went wrong in domain terms, and this module decides what that means over HTTP.

Goal 4 requires that an illegal move is rejected "with a message explaining why", so
the message is written where the rule lives and travels unchanged to the client.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError


class DomainError(Exception):
    """Base for every error the domain raises deliberately."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "domain_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(DomainError):
    """The row does not exist — or is not visible to this user.

    Deliberately conflated: telling an instructor that a booking exists but belongs
    to someone else's session leaks the existence of that session.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class PermissionDenied(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


class AuthenticationFailed(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_failed"


class RuleViolation(DomainError):
    """A well-formed request that the domain rules reject.

    422 rather than 400: the payload is valid, the *state* makes it impossible.
    """

    status_code = 422  # Unprocessable Content
    code = "rule_violation"


class IllegalTransition(RuleViolation):
    """A booking status change the state machine does not allow (goal 4)."""

    code = "illegal_transition"


class Conflict(DomainError):
    """A genuine concurrent-modification conflict: a stale version, a duplicate."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class LockTimeout(DomainError):
    """Contention exceeded ``lock_timeout``.

    503 with Retry-After rather than 429: nothing about the client was excessive.
    The server was briefly unable to serve, and the header says so.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "lock_timeout"


# Constraint names are stable because the schema names them explicitly and the
# metadata naming convention fills in the rest. Mapping here is what stops an
# integrity error surfacing as a 500 with a Postgres string in it.
CONSTRAINT_ERRORS: dict[str, tuple[type[DomainError], str]] = {
    "one_active_booking": (
        Conflict,
        "This member already has a booking on this session.",
    ),
    "no_room_overlap": (
        Conflict,
        "That room is already booked for an overlapping time.",
    ),
    "no_primary_instructor_overlap": (
        Conflict,
        "That instructor is already teaching an overlapping session.",
    ),
    "uq_users_email": (Conflict, "An account with that email already exists."),
    "uq_members_email": (Conflict, "A member with that email already exists."),
    "uq_rooms_name": (Conflict, "A room with that name already exists."),
    # Partial and case-insensitive, so this also fires when an archived class is
    # restored into a name that has since been taken — which is why the message
    # says "already offered" rather than "already created".
    "one_active_class_title": (
        Conflict,
        "A class with that title is already offered. Titles are compared without case.",
    ),
    "uq_dismissal_member_expiry": (
        Conflict,
        "That alert has already been dismissed.",
    ),
}

# PostgreSQL SQLSTATEs that mean "retry might work" rather than "you are wrong".
_LOCK_TIMEOUT = "55P03"
_DEADLOCK = "40P01"


def _constraint_name(exc: DBAPIError) -> str | None:
    orig = getattr(exc, "orig", None)
    for attr in ("constraint_name", "constraint"):
        name = getattr(orig, attr, None)
        if isinstance(name, str) and name:
            return name
    # asyncpg carries it on a nested exception object.
    inner = getattr(orig, "__cause__", None)
    name = getattr(inner, "constraint_name", None)
    return name if isinstance(name, str) and name else None


def _sqlstate(exc: DBAPIError) -> str | None:
    orig = getattr(exc, "orig", None)
    for attr in ("sqlstate", "pgcode"):
        code = getattr(orig, attr, None)
        if isinstance(code, str):
            return code
    inner = getattr(orig, "__cause__", None)
    code = getattr(inner, "sqlstate", None)
    return code if isinstance(code, str) else None


def translate_db_error(exc: DBAPIError) -> DomainError | None:
    """Turn a database error into a domain error, or None to let it 500.

    Letting something 500 is the right answer when it means the application has a
    bug — ``bookings_capacity_check`` firing, for instance, would mean a code path
    skipped the session lock, and dressing that up as a user-facing message would
    hide it.
    """
    name = _constraint_name(exc)
    if name and name in CONSTRAINT_ERRORS:
        error_cls, message = CONSTRAINT_ERRORS[name]
        return error_cls(message, constraint=name)

    state = _sqlstate(exc)
    if state == _LOCK_TIMEOUT:
        return LockTimeout("The system is busy. Please try again.")
    if state == _DEADLOCK:
        return LockTimeout("The request conflicted with another. Please try again.")
    return None


def _payload(exc: DomainError) -> dict[str, Any]:
    return {"code": exc.code, "message": exc.message, "details": exc.details}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        # Retry-After turns "not now" into something a client can act on rather
        # than guess at. Lock contention is over in about a second; a rate limit
        # carries its own remaining window.
        headers: dict[str, str] | None = None
        if isinstance(exc, LockTimeout):
            headers = {"Retry-After": "1"}
        elif "retry_after_seconds" in exc.details:
            headers = {"Retry-After": str(exc.details["retry_after_seconds"])}

        return JSONResponse(status_code=exc.status_code, content=_payload(exc), headers=headers)

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        translated = translate_db_error(exc)
        if translated is None:
            raise exc
        return await _domain(request, translated)

    @app.exception_handler(DBAPIError)
    async def _dbapi(request: Request, exc: DBAPIError) -> JSONResponse:
        translated = translate_db_error(exc)
        if translated is None:
            raise exc
        return await _domain(request, translated)
