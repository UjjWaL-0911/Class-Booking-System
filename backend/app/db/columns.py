"""Reusable column types.

Annotated aliases rather than helper functions, so a column declaration still reads
as a type annotation and SQLAlchemy's ``Mapped[...]`` inference keeps working.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from sqlalchemy import TIMESTAMP, Date, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import mapped_column

# Primary keys are uuid so identifiers are safe in URLs and do not leak row counts.
# gen_random_uuid() is built into PostgreSQL 13+; no extension needed.
UuidPk = Annotated[
    uuid.UUID,
    mapped_column(primary_key=True, server_default=text("gen_random_uuid()")),
]

UuidFk = Annotated[uuid.UUID, mapped_column()]

# Case-insensitive text. Used for email so "Ada@x.com" and "ada@x.com" are one
# person — the uniqueness constraint would be close to useless otherwise.
# Note: a trigram index on one of these is only used when the *query* casts to
# text. See docs/schema.md.
Email = Annotated[str, mapped_column(CITEXT)]

# Free text with no length limit. Postgres stores varchar and text identically,
# so an arbitrary cap would buy nothing and reject valid input.
Str = Annotated[str, mapped_column(Text)]

# Calendar date, not an instant: a membership expires at the end of a day in the
# studio's timezone, and attaching a time to that would invent precision.
CalendarDate = Annotated[dt.date, mapped_column(Date)]

# Every instant is timestamptz. The Base type_annotation_map already does this for
# bare `Mapped[datetime]`; this alias exists for columns that also need a default.
CreatedAt = Annotated[
    dt.datetime,
    mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False),
]
