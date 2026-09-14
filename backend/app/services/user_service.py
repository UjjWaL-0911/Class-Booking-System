"""Staff and instructor accounts.

The people who can sign in, as opposed to ``members``, who are records with no
login at all. Keeping the two apart is why this file is short: an account has a
name, an address, a role and a hash, and every interesting rule about what it may
then *do* lives in the role checks and the visibility filter rather than here.

Account creation is not one of the ten goals. It is here because the goals that do
exist assume it: goals 3, 5 and 7 take an instructor by id, and until now the only
way an instructor could come into being was the seed script. A studio that hires
somebody had no way to say so.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import UserCreate
from app.schemas.user import UserUpdate


class UserService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def list(self) -> Sequence[User]:
        """Active accounts of either role, ordered by name.

        Deliberately unpaginated: this is a studio's staff list, bounded by how
        many people it employs. A limit here would be a limit on a dropdown, and
        the day it triggered it would silently hide somebody's colleague.

        Deactivated accounts are excluded rather than shown greyed out. The two
        places this list is read are pickers for who may lead a class, and someone
        who has left the studio is not an answer to that question.

        **Members are excluded too, and that filter is load-bearing.** This list is
        what every instructor picker reads, so without it a self-service customer
        would appear as a candidate to lead a class — and ``SessionService``
        validates an instructor id against the same rule, so the two would agree
        and schedule them. The rule is named once, on the role itself, rather than
        written as ``!= MEMBER`` here: a fourth role should have to declare whether
        it can teach instead of inheriting an answer from how this line was phrased.
        """
        teaching_roles = [r for r in UserRole if r.is_teacher]
        query = (
            select(User)
            .where(User.is_active.is_(True), User.role.in_(teaching_roles))
            .order_by(User.full_name)
        )
        return (await self.db.execute(query)).scalars().all()

    async def create(self, payload: UserCreate) -> User:
        """Add a colleague.

        Hashing is argon2id through ``run_in_threadpool``, the same path sign-in
        takes — 100-500ms of deliberate CPU work that would otherwise block the
        event loop and, on a single instance, freeze every other in-flight request.

        A duplicate address raises ``uq_users_email``, which the error layer turns
        into a readable 409. Checking for one first would be a race rather than a
        safeguard: two people adding the same new instructor at once would both
        find nothing and both insert.
        """
        user = User(
            email=str(payload.email).strip(),
            full_name=payload.full_name.strip(),
            role=payload.role,
            password_hash=await hash_password(payload.password, self.settings),
            session_rate_minor=payload.session_rate_minor,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def set_rate(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        """Set or clear what a colleague is paid to lead one session.

        **A rate has no history, and that is a limitation rather than a design.**
        Changing it today changes what last month's payroll report says, because
        the report multiplies sessions by the rate as it stands now. For a studio
        whose rates change once a year that is the right trade — a rate history
        with effective dates is a second table, a temporal join in the payroll
        query, and a way to edit the past. It is the wrong trade the first time
        somebody gives an instructor a raise mid-month and needs the old figure
        back, and ``decisions.md`` records that as the point to revisit it.

        Inactive accounts are refused along with missing ones, matching the list:
        somebody who has left the studio is not a person to set a rate for, and
        distinguishing the two cases in the error would say more than the caller
        needs to know.
        """
        user = await self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise NotFound("No such person.")
        user.session_rate_minor = payload.session_rate_minor
        await self.db.flush()
        return user
