"""Expiring-membership alerts (goal 10).

Staff only. Goal 10 says "Studio staff can dismiss the alert", and the feed is
front-desk work — chasing renewals — rather than anything an instructor acts on.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import Config, DbSession, Now, StaffUser
from app.schemas.alerts import AlertCount, AlertFeed, MembershipAlert
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/memberships", response_model=AlertFeed, summary="Memberships needing attention")
async def membership_alerts(db: DbSession, settings: Config, now: Now, _: StaffUser) -> AlertFeed:
    """Members whose membership expires within the window, or already has.

    Suppressed for anyone whose *current* expiry has been dismissed — and no
    longer suppressed the moment that date changes, which is the re-trigger rule.
    """
    service = AlertService(db, settings)
    members, today = await service.feed(now)

    return AlertFeed(
        items=[
            MembershipAlert(
                member_id=m.id,
                full_name=m.full_name,
                email=m.email,
                membership_expiry=m.membership_expiry,
                days_remaining=(m.membership_expiry - today).days,
                has_expired=m.membership_expiry < today,
            )
            for m in members
        ],
        count=len(members),
        window_days=settings.membership_alert_window_days,
    )


@router.get(
    "/memberships/count",
    response_model=AlertCount,
    summary="Count for the navigation badge",
)
async def membership_alert_count(
    db: DbSession, settings: Config, now: Now, _: StaffUser
) -> AlertCount:
    """Separate from the feed because the badge is polled on every page load and
    the feed is opened rarely — sending every row to render one number would be
    the expensive way round."""
    return AlertCount(count=await AlertService(db, settings).count(now))


@router.post(
    "/memberships/{member_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dismiss a membership alert",
)
async def dismiss_membership_alert(
    member_id: uuid.UUID,
    db: DbSession,
    settings: Config,
    now: Now,
    staff: StaffUser,
) -> None:
    """Records the expiry date the alert was dismissed at.

    Storing the value rather than a boolean is what makes the alert return by
    itself when staff set a new date — nothing has to remember to undo this.
    """
    await AlertService(db, settings).dismiss(member_id, actor=staff, now=now)
    await db.commit()
