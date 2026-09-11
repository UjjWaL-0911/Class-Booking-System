"""The people who can be put in front of a class.

This endpoint exists because goals 3, 5 and 7 all take an instructor *by id* —
``primary_instructor_id`` when scheduling, ``user_id`` when adding a
co-instructor — and nothing else in the API can turn a person into an id. Without
it the only way to schedule a session is to read a uuid out of the database by
hand, which is not a scheduling feature.

It lists every **active** user rather than only ``role='instructor'``, because
that is exactly the rule ``SessionService._require_active_instructor`` enforces: a
staff member who also teaches is a real case, and a picker that hides them would
disagree with the server about who may lead a class. The role travels with each
row so the interface can say which is which.

Staff only. Instructors never call it — they do not schedule — and the names of
colleagues are not something an endpoint should hand out more widely than the
feature that needs it.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DbSession, StaffUser
from app.models.user import User
from app.schemas.auth import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut], summary="List people who can teach")
async def list_users(db: DbSession, _: StaffUser) -> list[UserOut]:
    """Active accounts, ordered by name.

    Deliberately unpaginated: this is a studio's staff list, bounded by how many
    people it employs. A limit here would be a limit on a dropdown, and the day it
    triggered it would silently hide somebody's colleague.
    """
    users = (
        (await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))
        .scalars()
        .all()
    )
    return [UserOut.model_validate(u) for u in users]
