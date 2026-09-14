"""Member endpoints.

Goal 1 assigns members to staff: "add members and set their membership expiry".
Instructors can read, but cannot create or edit — and they read a **scoped** set.

That scoping was added after the fact, and the reasoning it replaced is worth
recording: "an instructor can read members, because a class roster is names". The
flaw is that a roster is the names of people in *your* class, while this endpoint
served the whole binder — every member who ever joined, each with a membership
expiry beside them. An instructor covering one evening class could page through
the studio's entire membership.

Goal 1 scopes sessions rather than the directory, so the old behaviour was not a
breach of the letter of the brief. It was still the wrong default, and the fix
costs one clause: see ``visible_members_clause``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, StaffUser, StudioUser
from app.schemas.common import Page
from app.schemas.member import MemberCreate, MemberOut, MemberUpdate
from app.services.member_service import MemberService

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=Page[MemberOut], summary="List and search members")
async def list_members(
    db: DbSession,
    viewer: StudioUser,
    q: str | None = Query(
        default=None,
        max_length=100,
        description="Match against name or email.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[MemberOut]:
    """Search happens in the database, not the browser.

    The length cap on ``q`` matters: a trigram index stops helping once the search
    term is long enough that few trigrams are shared, and an unbounded term is a
    cheap way to force a sequential scan.
    """
    members, total = await MemberService(db, viewer).list(search=q, limit=limit, offset=offset)
    return Page[MemberOut](
        items=[MemberOut.model_validate(m) for m in members],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{member_id}", response_model=MemberOut, summary="Get one member")
async def get_member(member_id: uuid.UUID, db: DbSession, viewer: StudioUser) -> MemberOut:
    """404 rather than 403 for a member outside the viewer's scope — saying "this
    one exists but is not yours" would enumerate the membership one id at a time."""
    return MemberOut.model_validate(await MemberService(db, viewer).get(member_id))


@router.post(
    "",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member",
)
async def create_member(payload: MemberCreate, db: DbSession, staff: StaffUser) -> MemberOut:
    member = await MemberService(db, staff).create(payload)
    await db.commit()
    return MemberOut.model_validate(member)


@router.patch("/{member_id}", response_model=MemberOut, summary="Edit a member")
async def update_member(
    member_id: uuid.UUID, payload: MemberUpdate, db: DbSession, staff: StaffUser
) -> MemberOut:
    """Changing ``membership_expiry`` here also clears any dismissed expiry alert
    for this member — by database trigger, so it cannot be forgotten. See goal 10.
    """
    member = await MemberService(db, staff).update(member_id, payload)
    await db.commit()
    return MemberOut.model_validate(member)
