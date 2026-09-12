"""The people who can sign in, and adding one.

Reading this list exists because goals 3, 5 and 7 all take an instructor *by id* —
``primary_instructor_id`` when scheduling, ``user_id`` when adding a co-instructor
— and nothing else in the API can turn a person into an id. Without it the only
way to schedule a session is to read a uuid out of the database by hand, which is
not a scheduling feature.

It lists every **active** user rather than only ``role='instructor'``, because that
is exactly the rule ``SessionService._require_active_instructor`` enforces: a staff
member who also teaches is a real case, and a picker that hides them would disagree
with the server about who may lead a class. The role travels with each row so the
interface can say which is which.

Creating one is **not** a goal, and is recorded as a deliberate addition in
``decisions.md``. The goals assume it without asking for it: every one of them that
names an instructor assumes an instructor already exists, and until this endpoint
the only thing that could produce one was the seed script. A studio that hires
somebody in March had no way to tell the system.

Staff only, both of them. Instructors do not schedule, and the names of colleagues
are not something an endpoint should hand out more widely than the feature that
needs them.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.deps import Config, DbSession, StaffUser
from app.schemas.auth import UserCreate, UserOut
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut], summary="List people who can teach")
async def list_users(db: DbSession, settings: Config, _: StaffUser) -> list[UserOut]:
    users = await UserService(db, settings).list()
    return [UserOut.model_validate(u) for u in users]


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member of staff or an instructor",
)
async def create_user(
    payload: UserCreate, db: DbSession, settings: Config, _: StaffUser
) -> UserOut:
    """Staff add colleagues; nobody registers themselves.

    The response deliberately carries no password and no hash. ``UserOut`` has
    never had either field, which is why this endpoint needs no opinion about it —
    the shape that goes out is the same one the sign-in response uses.
    """
    user = await UserService(db, settings).create(payload)
    await db.commit()
    return UserOut.model_validate(user)
