"""FastAPI dependencies.

Kept in one place so the dependency chain for any endpoint can be read at a glance.

Goal 1 requires the role difference to be enforced on the server, "not just hidden
in the interface". ``require_role`` is the first of the mechanisms that does that;
the second — a query filter scoping instructors to their own sessions — arrives with
the session endpoints, and a third guards instructor writes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator, Callable
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationFailed, PermissionDenied
from app.core.rate_limit import LoginRateLimiter
from app.core.security import decode_access_token
from app.db.engine import get_session_factory
from app.models.enums import UserRole
from app.models.user import User


async def get_db() -> AsyncIterator[AsyncSession]:
    """Provide a session for the request and always close it.

    No transaction is opened here. Services decide their own boundaries, because in
    this system where a transaction begins and ends is a domain decision — the
    booking lock has to be taken and released at exactly the right points — not a
    request-lifecycle detail.
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


def get_config() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def get_login_rate_limiter() -> LoginRateLimiter:
    """The process-wide login limiter.

    Cached because the counters *are* the state — a fresh limiter per request
    would count to one forever. That also makes the single-instance assumption
    explicit: this object is the shared state, and it is not shared beyond the
    process.
    """
    settings = get_settings()
    return LoginRateLimiter(
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )


def utc_now() -> dt.datetime:
    """The current instant, as a dependency so tests can freeze it."""
    return dt.datetime.now(dt.UTC)


def client_ip(request: Request) -> str | None:
    """The caller's address, read from ``X-Forwarded-For``.

    The SPA's static host rewrites ``/api/*`` to this service, so
    ``request.client.host`` is always the proxy — the same value for every user.
    Anything reasoning about who is calling has to look past that hop, or per-IP
    rate limiting collapses into one global bucket.
    """
    settings = get_settings()
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return request.client.host if request.client else None

    # Right-most entries are added by infrastructure we control and can trust;
    # everything to the left is client-supplied and forgeable.
    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    index = len(hops) - 1 - settings.trusted_proxy_hops
    if 0 <= index < len(hops):
        return hops[index]
    return hops[0] if hops else None


DbSession = Annotated[AsyncSession, Depends(get_db)]
Config = Annotated[Settings, Depends(get_config)]
Now = Annotated[dt.datetime, Depends(utc_now)]
RateLimiter = Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)]
ClientIp = Annotated[str | None, Depends(client_ip)]


async def get_current_user(request: Request, db: DbSession) -> User:
    """Resolve the caller from the bearer token.

    The user row is loaded on every request rather than trusted from the token.
    That costs a round-trip and gives up part of the point of a stateless JWT — but
    it means deactivating an account takes effect immediately instead of whenever
    the token happens to expire, which for a system with two roles and a handful of
    users is the better trade.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationFailed("Not authenticated.")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailed("Your session has expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationFailed("Not authenticated.") from exc

    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationFailed("Not authenticated.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Restrict an endpoint to particular roles.

    Runs before the handler body, so an instructor calling a staff-only endpoint
    never reaches the service layer — regardless of what the interface showed them.
    """

    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDenied(
                "Your role does not have access to this action.",
                required=[r.value for r in roles],
            )
        return user

    return _check  # type: ignore[return-value]


StaffUser = Annotated[User, Depends(require_role(UserRole.STAFF))]
AnyUser = CurrentUser
