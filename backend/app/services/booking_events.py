"""The single place a row is appended to the booking timeline (goal 9).

Every status change in the system goes through ``record_event``. That is
deliberate: the timeline is append-only and enforced by database triggers, so a
change written without its event can never be corrected afterwards — the row
simply has no history and there is no way to add one.

Having one function also means the audit shape is defined once. When the
self-service phase adds a second kind of actor, it is a parameter change here
rather than fifteen call sites.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BookingEvent
from app.models.enums import BookingEventType, BookingStatus


def record_event(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    event_type: BookingEventType,
    occurred_at: dt.datetime,
    old_status: BookingStatus | None = None,
    new_status: BookingStatus | None = None,
    note: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    is_system: bool = False,
) -> BookingEvent:
    """Append one entry to a booking's timeline.

    Exactly one of ``actor_user_id`` and ``is_system`` identifies who acted.
    Automatic waitlist promotions and the bulk cancellation behind a session
    delete have no human actor, and recording the staff member who triggered them
    as though they made each individual change would be a small lie in an audit
    log — so those are marked ``is_system`` with a note saying what caused them.

    The event is added to the session but not committed: it must land in the same
    transaction as the change it describes, or a rollback would leave a history
    entry for something that never happened.
    """
    if is_system and actor_user_id is not None:
        raise ValueError("A system event cannot also have a human actor.")
    if not is_system and actor_user_id is None:
        raise ValueError("A non-system event must record who performed it.")

    event = BookingEvent(
        booking_id=booking_id,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
        note=note,
        actor_user_id=actor_user_id,
        is_system=is_system,
        occurred_at=occurred_at,
    )
    db.add(event)
    return event
