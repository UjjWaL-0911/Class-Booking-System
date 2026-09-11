"""Room endpoints.

Thin by design. Rooms exist so sessions have somewhere to be and so the overlap
constraint can join on an id rather than compare free text; nothing in the ten
goals asks for more than naming them and listing them.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import AnyUser, DbSession, StaffUser
from app.models.room import Room
from app.schemas.room import RoomCreate, RoomOut

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomOut], summary="List rooms")
async def list_rooms(db: DbSession, _: AnyUser) -> list[RoomOut]:
    rooms = (await db.execute(select(Room).order_by(Room.name))).scalars().all()
    return [RoomOut.model_validate(r) for r in rooms]


@router.post(
    "",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a room",
)
async def create_room(payload: RoomCreate, db: DbSession, _: StaffUser) -> RoomOut:
    # A duplicate name raises uq_rooms_name, which the error layer turns into a 409
    # with a readable message rather than a 500.
    room = Room(name=payload.name.strip())
    db.add(room)
    await db.commit()
    return RoomOut.model_validate(room)
