"""Shared response shapes."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A page of results, with the total number of matches.

    ``total`` is the count across the whole filtered set, not the page — goal 6
    requires "pagination showing the total number of matches", and a count of the
    rows returned would be useless for that.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PageParams(BaseModel):
    """Query parameters every paginated list accepts.

    The limit is capped: an unbounded page size is a denial-of-service vector and
    an accident waiting to happen on a 512 MB instance.
    """

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
