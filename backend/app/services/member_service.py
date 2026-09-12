"""Member management.

Goal 1 puts members in staff hands: "add members and set their membership expiry".
Goal 4 makes that expiry load-bearing — an expired member cannot create a booking —
and goal 10 turns it into the alerts feed. So this is a small CRUD service whose
one interesting column is read by two other parts of the system.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models.member import Member
from app.models.user import User
from app.repositories.visibility import visible_members_clause
from app.schemas.member import MemberCreate, MemberUpdate


def _search_clause(query: Select[tuple[Member]], term: str) -> Select[tuple[Member]]:
    """Filter on name or email.

    Note ``Member.email`` is cast to text. A trigram index *can* be built directly
    on a citext column, but the planner will not use it for citext-native
    operators — measured on 20,000 rows, the uncast form sequentially scans while
    this one uses the index. The results are identical either way, so the mistake
    is invisible outside the query plan.
    """
    pattern = f"%{term.strip()}%"
    return query.where(
        or_(
            Member.full_name.ilike(pattern),
            Member.email.cast(Text).ilike(pattern),
        )
    )


class MemberService:
    """Members, scoped to whoever is asking.

    The viewer is a constructor argument rather than a parameter on each read,
    because the alternative is a reader that is correct only while every call site
    remembers to pass it. Staff resolve to an unrestricted clause, so the scoping
    costs them nothing and cannot be forgotten by anyone.
    """

    def __init__(self, db: AsyncSession, viewer: User) -> None:
        self.db = db
        self.viewer = viewer

    async def list(
        self, *, search: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[Member], int]:
        """Return one page of members and the total matching the filter.

        Domain objects and a count, not a response model: shaping that into a
        wire format is the router's job, and a service that returns Pydantic
        models cannot be reused by anything that wants the rows themselves.
        """
        query = select(Member).where(visible_members_clause(self.viewer))
        if search:
            query = _search_clause(query, search)

        total = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()

        rows = (
            (
                await self.db.execute(
                    query.order_by(Member.full_name, Member.id).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )

        return rows, total

    async def get(self, member_id: uuid.UUID) -> Member:
        """One member, if this viewer may see them.

        A member outside the viewer's scope raises ``NotFound`` rather than a 403.
        Telling an instructor "that member exists but is not yours" would leak the
        existence of every member the rule is there to hide, one id at a time.
        """
        member = (
            await self.db.execute(
                select(Member).where(
                    Member.id == member_id,
                    visible_members_clause(self.viewer),
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise NotFound("No such member.")
        return member

    async def create(self, payload: MemberCreate) -> Member:
        # A duplicate email raises uq_members_email, which the error layer turns
        # into a readable 409. Checking first would be a race, not a safeguard.
        member = Member(
            full_name=payload.full_name.strip(),
            email=str(payload.email).strip(),
            membership_expiry=payload.membership_expiry,
            notes=payload.notes.strip(),
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def update(self, member_id: uuid.UUID, payload: MemberUpdate) -> Member:
        """Apply a partial update.

        No version token here, unlike classes and sessions. Member records are
        edited rarely and by one person at a time at a front desk, and the cost of
        a lost update is a re-typed phone number rather than an oversold class.
        """
        member = await self.get(member_id)
        changes = payload.model_dump(exclude_none=True)
        for field, value in changes.items():
            setattr(member, field, value.strip() if isinstance(value, str) else value)
        await self.db.flush()
        return member

    async def is_expired(self, member: Member, today: dt.date) -> bool:
        """A membership is valid *through* its expiry date, not up to it."""
        return member.membership_expiry < today
