"""Class endpoints (goal 2).

Reading is open to any signed-in user: an instructor needs the title and discipline
of the class their session belongs to. Writing is staff-only, enforced by a
dependency that runs before the handler body — so an instructor calling these gets
a 403 regardless of what the interface offered them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, Now, StaffUser, StudioUser
from app.schemas.studio_class import ClassCreate, ClassOut, ClassUpdate
from app.services.class_service import ClassService

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("", response_model=list[ClassOut], summary="List classes")
async def list_classes(
    db: DbSession,
    _: StudioUser,
    include_archived: bool = Query(
        default=False,
        description="Archived classes are hidden unless explicitly requested.",
    ),
) -> list[ClassOut]:
    classes = await ClassService(db).list(include_archived=include_archived)
    return [ClassOut.model_validate(c) for c in classes]


@router.get("/{class_id}", response_model=ClassOut, summary="Get one class")
async def get_class(class_id: uuid.UUID, db: DbSession, _: StudioUser) -> ClassOut:
    return ClassOut.model_validate(await ClassService(db).get(class_id))


@router.post(
    "",
    response_model=ClassOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a class",
)
async def create_class(payload: ClassCreate, db: DbSession, _: StaffUser) -> ClassOut:
    studio_class = await ClassService(db).create(payload)
    await db.commit()
    return ClassOut.model_validate(studio_class)


@router.patch("/{class_id}", response_model=ClassOut, summary="Edit a class")
async def update_class(
    class_id: uuid.UUID, payload: ClassUpdate, db: DbSession, _: StaffUser
) -> ClassOut:
    studio_class = await ClassService(db).update(class_id, payload)
    await db.commit()
    return ClassOut.model_validate(studio_class)


@router.post("/{class_id}/archive", response_model=ClassOut, summary="Archive a class")
async def archive_class(class_id: uuid.UUID, db: DbSession, now: Now, _: StaffUser) -> ClassOut:
    """Hide the class from default views without touching its sessions or bookings."""
    studio_class = await ClassService(db).archive(class_id, now)
    await db.commit()
    return ClassOut.model_validate(studio_class)


@router.post("/{class_id}/restore", response_model=ClassOut, summary="Restore a class")
async def restore_class(class_id: uuid.UUID, db: DbSession, _: StaffUser) -> ClassOut:
    studio_class = await ClassService(db).restore(class_id)
    await db.commit()
    return ClassOut.model_validate(studio_class)
