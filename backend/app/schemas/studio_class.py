"""Class request and response bodies (goal 2)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ClassCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    discipline: str = Field(min_length=1, max_length=100)
    # Bounded on both sides: a zero-minute class is meaningless and a 24-hour one
    # is a typo. The database CHECK guards the lower bound regardless of this.
    default_duration_min: int = Field(gt=0, le=600)
    default_capacity: int = Field(gt=0, le=1000)


class ClassUpdate(BaseModel):
    """Every field optional — this is a PATCH.

    ``version`` is required, and is what makes a stale edit form fail loudly
    instead of silently overwriting someone else's change.
    """

    version: int
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    discipline: str | None = Field(default=None, min_length=1, max_length=100)
    default_duration_min: int | None = Field(default=None, gt=0, le=600)
    default_capacity: int | None = Field(default=None, gt=0, le=1000)


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    discipline: str
    default_duration_min: int
    default_capacity: int
    archived_at: dt.datetime | None
    version: int
    created_at: dt.datetime
    updated_at: dt.datetime

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
