"""Member request and response bodies.

A member is a customer record. It may *also* have a login, which staff switch on
one member at a time — see ``MemberAccountCreate``. Most members have neither and
never will: somebody who rings the desk to book is served exactly as before, and
nothing about these shapes changed when self-service arrived.

The credential itself is never in this file. It lives on ``users``, and a member
record points at it; ``MemberOut`` says only *whether* there is one.
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


class MemberAccountCreate(BaseModel):
    """Give one existing member a login, so they can book for themselves.

    **There is no public sign-up, and that is the decision this schema encodes.**
    The same argument that keeps staff registration closed applies here and is
    stronger: a member account implies a membership, a membership implies somebody
    paid, and an endpoint on the open internet cannot know that. Self-registration
    would either grant a membership nobody agreed to, or create accounts that can
    do nothing until the desk intervenes anyway.

    Letting a stranger *claim* an existing member record would be worse. There is
    no mail sender here, so nothing can prove the person owns the address — and
    the record they would be claiming carries somebody's booking history.

    So a member gets a login the way a colleague does: somebody already inside
    vouches for them and hands the password over in person. The same genuine
    limitation as ``UserCreate``, for the same missing reason, with the same
    twelve-character floor compensating for a password that cannot yet be changed
    from inside the app.

    No email field: the account signs in with the address already on the member
    record, because two addresses for one person is a support call waiting to
    happen.
    """

    password: str = Field(min_length=12)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    membership_expiry: dt.date
    notes: str
    created_at: dt.datetime
    updated_at: dt.datetime

    # Whether this member can sign in — not the account, and certainly not the
    # hash. A boolean is everything the desk needs to know and the most the
    # interface should ever be told.
    has_login: bool = False
