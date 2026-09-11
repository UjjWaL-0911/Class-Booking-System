"""Member request and response bodies.

Members are customer records, not accounts: no password, no login. Goal 1 gives
sign-in to staff and instructors only, and bookings are created *for* a member by
staff.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MemberCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    membership_expiry: dt.date
    notes: str = Field(default="", max_length=2000)


class MemberUpdate(BaseModel):
    """Partial update. Includes ``membership_expiry``, which is how goal 1's "set
    their membership expiry" is done — and changing it clears any dismissed
    expiry alert, by database trigger."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    membership_expiry: dt.date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    membership_expiry: dt.date
    notes: str
    created_at: dt.datetime
    updated_at: dt.datetime
