"""Authentication request and response bodies."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    # No maximum-length rule and no composition rules: the only property that
    # matters here is that it is not empty, and argon2 handles any length.
    password: str = Field(min_length=1)


class UserCreate(BaseModel):
    """A new staff or instructor account, created by a member of staff.

    There is no public registration, and that is the decision this schema encodes.
    A studio's back office is not something people join by finding the URL: the
    account already implies a relationship with the studio, and the person who can
    vouch for it is the one already inside. Self-registration would also let the
    applicant choose their own ``role``, which would make goal 1's server-side
    enforcement decorative.

    The password is set by whoever creates the account and handed over in person.
    That is a genuine limitation rather than a design: there is no mail sender, so
    an invitation link has nothing to travel on. The twelve-character minimum is
    the compensation — an initial password that cannot yet be changed from inside
    the app should not also be short.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    password: str = Field(min_length=12)

    # Optional, and its absence means "not decided yet" rather than "unpaid" —
    # the desk adding an instructor on a Monday morning should not be blocked on
    # a number that has to come from whoever agrees rates. Bounds and units are
    # documented on ``schemas/user.UserUpdate``, which is where it is changed.
    session_rate_minor: int | None = Field(default=None, ge=0, le=2_147_483_647)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole


class TokenResponse(BaseModel):
    """The access token, plus who it belongs to.

    The refresh token is deliberately absent: it travels only as an httpOnly
    cookie, so JavaScript can never read it and an XSS bug cannot exfiltrate a
    long-lived credential.
    """

    access_token: str
    token_type: str = "bearer"  # noqa: S105 — a scheme name, not a secret
    expires_at: dt.datetime
    user: UserOut
