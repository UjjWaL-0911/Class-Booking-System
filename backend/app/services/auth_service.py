"""Authentication: login, refresh rotation, logout.

This service owns its transactions and never imports ``fastapi``. What a cookie is
called and how it is set is the router's problem; what a valid session *is* belongs
here.

Goal 1 needs people to sign in with an email and password. The refresh-token
machinery exists because the alternative — a single long-lived access token — has no
way to be revoked, so logging out would be a lie and deactivating an account would
take until the token expired.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationFailed
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User

# Deliberately identical for "no such account" and "wrong password": distinguishing
# them tells an attacker which emails are registered.
_BAD_CREDENTIALS = "Incorrect email or password."


class IssuedSession:
    """What a successful login or refresh produces."""

    __slots__ = ("access_token", "expires_at", "refresh_token", "user")

    def __init__(
        self,
        *,
        user: User,
        access_token: str,
        expires_at: dt.datetime,
        refresh_token: str,
    ) -> None:
        self.user = user
        self.access_token = access_token
        self.expires_at = expires_at
        self.refresh_token = refresh_token


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------ login

    async def login(
        self,
        *,
        email: str,
        password: str,
        now: dt.datetime,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> IssuedSession:
        user = (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none()

        if user is None:
            # Still hash something, so a missing account does not answer faster
            # than a wrong password and reveal itself by timing.
            await verify_password(_DUMMY_HASH, password, self.settings)
            raise AuthenticationFailed(_BAD_CREDENTIALS)

        if not await verify_password(user.password_hash, password, self.settings):
            raise AuthenticationFailed(_BAD_CREDENTIALS)

        if not user.is_active:
            raise AuthenticationFailed("This account has been deactivated.")

        await self._prune_expired(user.id, now)
        _, raw = await self._issue_refresh(
            user_id=user.id,
            family_id=uuid.uuid4(),  # a new login starts a new lineage
            now=now,
            user_agent=user_agent,
            client_ip=client_ip,
        )
        return self._issue(user, raw, now)

    # ---------------------------------------------------------------- refresh

    async def refresh(
        self,
        *,
        token: str,
        now: dt.datetime,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> IssuedSession:
        """Rotate a refresh token, detecting reuse.

        Every refresh revokes the presented row and issues a successor in the same
        family. If an already-rotated token comes back, a copy is circulating and
        the whole family is revoked — which is the entire point of rotating.
        """
        row = (
            await self.db.execute(
                select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
            )
        ).scalar_one_or_none()

        if row is None or row.expires_at <= now:
            raise AuthenticationFailed("Your session has expired. Please sign in again.")

        if row.revoked_at is not None:
            return await self._handle_revoked(row, now)

        user = await self._active_user(row.user_id)
        row.revoked_at = now
        successor, raw = await self._issue_refresh(
            user_id=user.id,
            family_id=row.family_id,
            now=now,
            user_agent=user_agent,
            client_ip=client_ip,
        )
        row.replaced_by_id = successor.id
        await self.db.flush()
        return self._issue(user, raw, now)

    async def _handle_revoked(self, row: RefreshToken, now: dt.datetime) -> IssuedSession:
        """A token that has already been rotated came back.

        Usually that is several browser tabs refreshing at once rather than an
        attack, so a short grace window re-issues the *existing* successor instead
        of minting a new one — the lineage does not grow, and a genuine race
        degrades to a retry rather than a logout.

        Outside the window it is treated as reuse: the whole family is revoked.
        This is a real trade, made explicitly. Inside those few seconds, reuse
        detection is off.
        """
        grace = dt.timedelta(seconds=self.settings.refresh_grace_seconds)
        within_grace = row.revoked_at is not None and now - row.revoked_at <= grace

        if within_grace and row.replaced_by_id is not None:
            successor = (
                await self.db.execute(
                    select(RefreshToken).where(RefreshToken.id == row.replaced_by_id)
                )
            ).scalar_one_or_none()
            if successor is not None and successor.is_usable(now):
                user = await self._active_user(row.user_id)
                # An empty refresh_token tells the router to leave the cookie
                # alone: the successor's raw value cannot be recovered from its
                # hash, and the caller that won the race already holds it.
                return self._issue(user, "", now)

        await self.revoke_family(row.family_id, now)
        # Committed here rather than left to the router, which is the one place in
        # this service that does so. The exception below aborts the request, and
        # with it the transaction — so without an explicit commit the revocation
        # would be rolled back by the very error that reports it, and reuse
        # detection would return 401 while protecting nothing.
        await self.db.commit()
        raise AuthenticationFailed("This session is no longer valid. Please sign in again.")

    # ----------------------------------------------------------------- logout

    async def logout(self, *, token: str | None, now: dt.datetime) -> None:
        """Revoke the presented session. Silent when there is nothing to revoke.

        Logging out is not an operation that can meaningfully fail, and reporting
        "that token was already invalid" would only tell an attacker something.
        """
        if not token:
            return
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_refresh_token(token),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def revoke_family(self, family_id: uuid.UUID, now: dt.datetime) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    # ---------------------------------------------------------------- helpers

    async def _active_user(self, user_id: uuid.UUID) -> User:
        user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None or not user.is_active:
            raise AuthenticationFailed("This account is no longer active.")
        return user

    async def _issue_refresh(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        now: dt.datetime,
        user_agent: str | None,
        client_ip: str | None,
    ) -> tuple[RefreshToken, str]:
        raw = generate_refresh_token()
        row = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(raw),
            issued_at=now,
            expires_at=now + dt.timedelta(days=self.settings.refresh_token_ttl_days),
            user_agent=user_agent,
            client_ip=client_ip,
        )
        self.db.add(row)
        await self.db.flush()
        # The raw token is returned alongside the row rather than stored on it: it
        # exists for exactly one response and cannot be recovered from the hash.
        return row, raw

    def _issue(self, user: User, refresh_token: str, now: dt.datetime) -> IssuedSession:
        access_token, expires_at = create_access_token(
            user_id=user.id, role=user.role.value, now=now, settings=self.settings
        )
        return IssuedSession(
            user=user,
            access_token=access_token,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    async def _prune_expired(self, user_id: uuid.UUID, now: dt.datetime) -> None:
        """Opportunistic cleanup on login, rather than a scheduled job.

        ``replaced_by_id`` is ON DELETE SET NULL for this: with the default NO
        ACTION, deleting an expired predecessor that a surviving row still points
        at would raise a foreign-key violation — in production, and never in a test.
        """
        await self.db.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.expires_at < now
            )
        )


# A valid argon2 hash of a value nobody knows, used only to keep the timing of a
# missing account indistinguishable from a wrong password.
_DUMMY_HASH = (
    "$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHR2YWx1ZQ$Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFy"
)
