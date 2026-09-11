"""Expiring-membership alerts (goal 10).

The interesting requirement is the last sentence: "If staff set a new, later expiry
date and that date later falls within seven days again, the alert returns."

That is not implemented here at all, which is the point. A dismissal row records
the expiry date that was current when it was dismissed, and an alert is suppressed
only when a dismissal matches the member's *present* expiry. Set a new date and no
dismissal matches it, so the alert comes back on its own once that date enters the
window — no background job, no flag to reset, and therefore no reset that can fail.

A database trigger additionally clears a member's dismissals whenever their expiry
changes at all, which closes the one case value-matching misses: dismiss, extend the
expiry, then correct it back to the original date.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NotFound, RuleViolation
from app.core.time import today as studio_today
from app.models.member import Member, MembershipAlertDismissal
from app.models.user import User


class AlertService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def _alerting(self, today: dt.date):  # type: ignore[no-untyped-def]
        """The rule, as a WHERE clause.

        A member alerts when their expiry falls inside the window *or has already
        passed* — goal 10 asks for both — unless a dismissal exists matching the
        expiry they have right now.
        """
        cutoff = today + dt.timedelta(days=self.settings.membership_alert_window_days)
        dismissed = exists().where(
            and_(
                MembershipAlertDismissal.member_id == Member.id,
                MembershipAlertDismissal.dismissed_expiry == Member.membership_expiry,
            )
        )
        return and_(Member.membership_expiry <= cutoff, ~dismissed)

    async def feed(self, now: dt.datetime) -> tuple[Sequence[Member], dt.date]:
        """Members needing attention, soonest expiry first.

        Already-expired members sort to the top, because they are the ones who can
        no longer book and are most likely to turn up anyway.
        """
        today = studio_today(self.settings.tz, now)
        rows = (
            (
                await self.db.execute(
                    select(Member)
                    .where(self._alerting(today))
                    .order_by(Member.membership_expiry, Member.full_name)
                )
            )
            .scalars()
            .all()
        )
        return rows, today

    async def count(self, now: dt.datetime) -> int:
        """Just the number, for the navigation badge.

        A count query rather than len() of the feed: the badge is polled on every
        page, and fetching every row to render one number would be the expensive
        way round.
        """
        today = studio_today(self.settings.tz, now)
        return (
            await self.db.execute(
                select(func.count()).select_from(Member).where(self._alerting(today))
            )
        ).scalar_one()

    async def dismiss(
        self, member_id: uuid.UUID, *, actor: User, now: dt.datetime
    ) -> MembershipAlertDismissal:
        """Dismiss one member's alert, recording the expiry it was dismissed at.

        Storing the *value* rather than a boolean is what makes the re-trigger rule
        work without anything having to remember to undo it.
        """
        member = (
            await self.db.execute(select(Member).where(Member.id == member_id))
        ).scalar_one_or_none()
        if member is None:
            raise NotFound("No such member.")

        today = studio_today(self.settings.tz, now)
        cutoff = today + dt.timedelta(days=self.settings.membership_alert_window_days)
        if member.membership_expiry > cutoff:
            raise RuleViolation(
                "This membership is not expiring soon, so there is no alert to dismiss."
            )

        already = (
            await self.db.execute(
                select(MembershipAlertDismissal).where(
                    MembershipAlertDismissal.member_id == member_id,
                    MembershipAlertDismissal.dismissed_expiry == member.membership_expiry,
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            return already

        dismissal = MembershipAlertDismissal(
            member_id=member_id,
            dismissed_expiry=member.membership_expiry,
            dismissed_by=actor.id,
            dismissed_at=now,
        )
        self.db.add(dismissal)
        await self.db.flush()
        return dismissal
