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
