"""Expiring-membership alerts (goal 10)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class MembershipAlert(BaseModel):
    member_id: uuid.UUID
    full_name: str
    email: str
    membership_expiry: dt.date

    # Negative once the date has passed, which is what lets a client sort the
    # already-expired to the top without re-deriving it.
    days_remaining: int
    has_expired: bool


class AlertFeed(BaseModel):
    items: list[MembershipAlert]
    count: int
    window_days: int


class AlertCount(BaseModel):
    """Just the number, for the navigation badge.

    A separate endpoint because the badge is polled on every page while the feed
    itself is opened rarely, and sending the whole list to render a number would
    be the expensive way to do it.
    """

    count: int
