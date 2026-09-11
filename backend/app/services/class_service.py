"""Class management (goal 2).

Archiving is the only part with any subtlety. It is not deletion: sessions and
bookings are untouched, the class disappears from default views, and clearing the
timestamp brings it back exactly as it was. It does have one behavioural
consequence — a class that is no longer offered should not take new sign-ups — and
that rule is enforced by the booking service, not here.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, RuleViolation
from app.models.studio_class import StudioClass
from app.schemas.studio_class import ClassCreate, ClassUpdate


class ClassService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, *, include_archived: bool = False) -> Sequence[StudioClass]:
        """Archived classes are hidden by default — that is what archiving means."""
        query = select(StudioClass).order_by(StudioClass.title)
        if not include_archived:
            query = query.where(StudioClass.archived_at.is_(None))
        return (await self.db.execute(query)).scalars().all()

    async def get(self, class_id: uuid.UUID) -> StudioClass:
        """Fetch by id, archived or not.

        A direct link to an archived class still resolves: hiding it from lists is
        the point, making its bookings unreachable is not.
        """
        studio_class = (
            await self.db.execute(select(StudioClass).where(StudioClass.id == class_id))
        ).scalar_one_or_none()
        if studio_class is None:
            raise NotFound("No such class.")
        return studio_class

    async def create(self, payload: ClassCreate) -> StudioClass:
        studio_class = StudioClass(
            title=payload.title.strip(),
            description=payload.description.strip(),
            discipline=payload.discipline.strip(),
            default_duration_min=payload.default_duration_min,
            default_capacity=payload.default_capacity,
        )
        self.db.add(studio_class)
        await self.db.flush()
        return studio_class

    async def update(self, class_id: uuid.UUID, payload: ClassUpdate) -> StudioClass:
        """Apply a partial update, rejecting a stale edit form.

        The version check is what turns "two staff had the class open and both hit
        save" from a silent last-write-wins into a visible 409. It is checked here
        rather than left to SQLAlchemy's ``version_id_col``, because the ORM
        compares against the version *this* transaction loaded — it cannot know the
        client's form was rendered from an older one.
        """
        studio_class = await self.get(class_id)

        if studio_class.version != payload.version:
            raise Conflict(
                "This class was changed by someone else. Reload and try again.",
                expected=payload.version,
                actual=studio_class.version,
            )

        changes = payload.model_dump(exclude={"version"}, exclude_none=True)
        for field, value in changes.items():
            setattr(studio_class, field, value.strip() if isinstance(value, str) else value)

        # SQLAlchemy only bumps version_id_col when it detects a change, so a PATCH
        # that alters nothing leaves the version alone — which is correct: there is
        # nothing for a concurrent editor to have missed.
        await self.db.flush()
        return studio_class

    async def archive(self, class_id: uuid.UUID, now: dt.datetime) -> StudioClass:
        studio_class = await self.get(class_id)
        if studio_class.archived_at is not None:
            raise RuleViolation("This class is already archived.")
        studio_class.archived_at = now
        await self.db.flush()
        return studio_class

    async def restore(self, class_id: uuid.UUID) -> StudioClass:
        studio_class = await self.get(class_id)
        if studio_class.archived_at is None:
            raise RuleViolation("This class is not archived.")
        studio_class.archived_at = None
        await self.db.flush()
        return studio_class
