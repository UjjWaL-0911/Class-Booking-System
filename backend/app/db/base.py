"""Declarative base and shared column mixins.

Two things here are load-bearing beyond ordinary boilerplate:

* **The naming convention.** Every constraint gets a predictable name, because the
  error-mapping layer dispatches on constraint name to turn an integrity error into
  a useful 409 rather than a 500. Constraints the design names explicitly
  (``one_active_booking``, ``no_room_overlap``, ``bookings_capacity_check``) keep
  those names; the convention only fills in the ones we do not name by hand.

* **``datetime`` maps to ``TIMESTAMP(timezone=True)``.** Without this, a bare
  ``Mapped[datetime]`` silently produces ``timestamp without time zone``, and every
  date-bucketed query in goals 8 and 10 would be wrong in a way nothing would catch.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import TIMESTAMP, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every naive `Mapped[datetime]` becomes timestamptz. See the module docstring.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dt.datetime: TIMESTAMP(timezone=True),
    }

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        """Fetch database-generated values with RETURNING, at flush time.

        Without this, a column filled in by a trigger or a server default is left
        expired after the write, and reading it later raises MissingGreenlet — the
        async engine refusing to perform IO from a synchronous attribute access.
        The two tables that also carry a version counter override this to add
        ``version_id_col``.
        """
        return {"eager_defaults": True}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={getattr(self, 'id', None)}>"


class TimestampMixin:
    """``created_at`` / ``updated_at`` on every mutable table.

    Both defaults are ``server_default``, not Python-side: the value must be right
    no matter which code path writes the row, including a migration or a manual fix.
    ``updated_at`` is additionally maintained by a database trigger, for the same
    reason — see docs/schema.md.
    """

    @declared_attr
    def created_at(cls) -> Mapped[dt.datetime]:
        return mapped_column(server_default=func.now(), nullable=False)

    @declared_attr
    def updated_at(cls) -> Mapped[dt.datetime]:
        return mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
