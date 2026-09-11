"""Authentication endpoints (goal 1).

The router owns transport concerns only: reading the cookie, setting it, and turning
an ``IssuedSession`` into a response body. Every rule about what a valid session is
lives in ``AuthService``.

The refresh cookie is ``httpOnly`` + ``Secure`` + ``SameSite=Lax``. Lax rather than
None is possible because the SPA and this API share one origin — the static host
rewrites ``/api/*`` here — which also means there is no CORS configuration at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
from app.core.deps import (
    ClientIp,
    Config,
    CurrentUser,
    DbSession,
    Now,
    RateLimiter,
)
from app.core.errors import AuthenticationFailed
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services.auth_service import AuthService, IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])

# A non-simple header on the refresh endpoint. It forces a CORS preflight that a
# foreign origin cannot satisfy, which is what stops another site silently calling
# /auth/refresh with the ambient cookie and rotating a victim's session out from
# under them. Checked alongside Origin below.
CSRF_HEADER = "x-refresh-request"


def _set_refresh_cookie(response: Response, token: str, settings: Settings, *, local: bool) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        httponly=True,
        # Secure is dropped for local http development only; everywhere else the
        # cookie must never travel in the clear.
        secure=not local,
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )


def _respond(
    session: IssuedSession, response: Response, settings: Settings, *, local: bool
) -> TokenResponse:
    # An empty refresh token means the grace path re-issued an access token without
    # rotating; the caller's existing cookie is still the valid one, so leave it.
    if session.refresh_token:
        _set_refresh_cookie(response, session.refresh_token, settings, local=local)
    return TokenResponse(
        access_token=session.access_token,
        expires_at=session.expires_at,
        user=UserOut.model_validate(session.user),
    )


def _guard_csrf(request: Request) -> None:
    if request.headers.get(CSRF_HEADER) is None:
        raise AuthenticationFailed("Missing required header for this request.", header=CSRF_HEADER)
    origin = request.headers.get("origin")
    # Absent Origin fails closed: every browser context that legitimately reaches
    # this endpoint sends one, so a missing header is not a browser we recognise.
    if origin is None:
        raise AuthenticationFailed("Request origin could not be verified.")


@router.post("/login", response_model=TokenResponse, summary="Sign in")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: Config,
    now: Now,
    ip: ClientIp,
    limiter: RateLimiter,
) -> TokenResponse:
    """Sign in with an email and password (goal 1).

    Rate limited per email and per forwarded address, and checked *before* the
    password is verified: checking afterwards would still hand an attacker one
    argon2 hash per attempt, which is the expensive thing being protected.
    """
    limiter.check(email=body.email, client_ip=ip)

    service = AuthService(db, settings)
    session = await service.login(
        email=body.email,
        password=body.password,
        now=now,
        user_agent=request.headers.get("user-agent"),
        client_ip=ip,
    )
    await db.commit()

    # Cleared on success, so four typos followed by the right password does not
    # leave somebody one attempt from a lockout for the rest of the window.
    limiter.reset(email=body.email, client_ip=ip)

    return _respond(session, response, settings, local=not settings.is_production)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the session")
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    settings: Config,
    now: Now,
    ip: ClientIp,
) -> TokenResponse:
    _guard_csrf(request)
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise AuthenticationFailed("Not authenticated.")

    service = AuthService(db, settings)
    session = await service.refresh(
        token=token,
        now=now,
        user_agent=request.headers.get("user-agent"),
        client_ip=ip,
    )
    await db.commit()
    return _respond(session, response, settings, local=not settings.is_production)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End the session")
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    settings: Config,
    now: Now,
) -> Response:
    service = AuthService(db, settings)
    await service.logout(token=request.cookies.get(settings.refresh_cookie_name), now=now)
    await db.commit()
    response.delete_cookie(settings.refresh_cookie_name, path="/api/v1/auth")
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=response.headers)


@router.get("/me", response_model=UserOut, summary="The signed-in user")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
