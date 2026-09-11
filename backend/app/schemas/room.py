"""Room request and response bodies.

Rooms exist because sessions need somewhere to be, and because overlap detection
joins on ``room_id`` rather than comparing free text. They are deliberately thin:
nothing in the ten goals asks for room management beyond naming them.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
