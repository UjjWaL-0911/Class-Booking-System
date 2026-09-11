"""Password hashing, access tokens, and opaque refresh tokens.

No database access and no domain logic — this module knows how to hash, sign and
verify, and nothing about users or sessions. That separation is what lets the auth
service be tested without cryptography and this be tested without a database.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings

_TOKEN_BYTES = 32


def _hasher(settings: Settings) -> PasswordHasher:
    """Argon2id at the OWASP baseline, not the library default.

    argon2-cffi defaults to 64 MiB per hash. A handful of concurrent logins at that
    size is an out-of-memory kill on a 512 MB instance, so memory_cost is set to the
    OWASP-recommended 19 MiB and the threadpool that runs these is capped to match.
    """
    return PasswordHasher(
        memory_cost=settings.argon2_memory_cost_kib,
        time_cost=settings.argon2_time_cost,
        parallelism=settings.argon2_parallelism,
    )


async def hash_password(password: str, settings: Settings | None = None) -> str:
    """Hash a password without blocking the event loop.

    Argon2 is 100-500 ms of deliberate CPU work. Called directly inside an
    ``async def`` handler it stalls the entire worker — on a single free-tier
    instance that freezes every other in-flight request, which makes "async end to
    end" untrue in exactly the moment it matters.
    """
    settings = settings or get_settings()
    return await run_in_threadpool(_hasher(settings).hash, password)


async def verify_password(
    password_hash: str, password: str, settings: Settings | None = None
) -> bool:
    """Verify a password. Returns False rather than raising on a mismatch."""
    settings = settings or get_settings()

    def _verify() -> bool:
        try:
            return _hasher(settings).verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    return await run_in_threadpool(_verify)


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    now: dt.datetime,
    settings: Settings | None = None,
) -> tuple[str, dt.datetime]:
    """Mint a short-lived access token. Returns the token and its expiry.

    The role travels in the token so the client can shape its interface, but the
    server never trusts it for authorization: every request re-loads the user, so a
    deactivated account or a changed role takes effect immediately.
    """
    settings = settings or get_settings()
    expires_at = now + dt.timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": "access",
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, expires_at


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Verify and decode an access token.

    Raises ``jwt.PyJWTError`` on anything wrong: bad signature, expiry, or a token
    minted for another purpose. The ``typ`` check matters — without it a refresh
    token, if it were ever a JWT, would be accepted here.
    """
    settings = settings or get_settings()
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "typ"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


def generate_refresh_token() -> str:
    """A random opaque string, deliberately not a JWT.

    Its only job is to be looked up and revoked. Signing it would imply a
    self-validation it does not have, and would not make revocation possible.
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Store only the hash, so a database leak yields no usable tokens.

    Plain SHA-256 rather than argon2: the input is 32 bytes of cryptographic
    randomness, so there is no low-entropy secret to slow an attacker down over,
    and this runs on every refresh.
    """
    return hashlib.sha256(token.encode()).hexdigest()
