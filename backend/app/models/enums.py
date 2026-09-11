"""Domain enumerations.

Each is a native PostgreSQL ``ENUM`` rather than a check-constrained string: an
invalid value then fails at the database, not merely in the layer that remembered
to validate. ``values_callable`` makes the stored labels the lower-case values
("staff"), not the Python member names ("STAFF").
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class UserRole(StrEnum):
    """Goal 1's two roles. Members are records, not accounts, so they are absent."""

    STAFF = "staff"
    INSTRUCTOR = "instructor"


class BookingStatus(StrEnum):
    """The booking lifecycle from goal 4.

    ``BOOKED`` and ``WAITLISTED`` are the two active states — the ones the partial
    unique index treats as "this member already has a place". The other three are
    terminal.
    """

    BOOKED = "booked"
    WAITLISTED = "waitlisted"
    CANCELLED = "cancelled"
    ATTENDED = "attended"
    NO_SHOW = "no_show"

    @property
    def label(self) -> str:
        """How this status is written wherever a person reads it.

        Here rather than derived from the value, because the two are not the same
        thing and should be free to differ: ``no_show`` is the stored value —
        changing it means a migration and an enum rewrite — while "Absent" is
        wording, and wording is allowed to change on a Tuesday.

        It is also a single place on purpose. This label previously existed three
        times: once in the CSV export and twice as
        ``status.value.replace('_', ' ').title()`` inside error messages, which
        meant the wording could not be changed at all in two of the three.

        "Absent" rather than "No Show": it is the word a class register uses, it
        is the true opposite of "Attended" so the pair reads as one decision, and
        it describes the member rather than passing judgement on them.
        """
        return {
            BookingStatus.BOOKED: "Booked",
            BookingStatus.WAITLISTED: "Waitlisted",
            BookingStatus.CANCELLED: "Cancelled",
            BookingStatus.ATTENDED: "Attended",
            BookingStatus.NO_SHOW: "Absent",
        }[self]

    @classmethod
    def active(cls) -> tuple[BookingStatus, ...]:
        return (cls.BOOKED, cls.WAITLISTED)

    @classmethod
    def terminal(cls) -> tuple[BookingStatus, ...]:
        return (cls.CANCELLED, cls.ATTENDED, cls.NO_SHOW)


class BookingEventType(StrEnum):
    """What a row in the append-only timeline records (goal 9)."""

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    NOTE_ADDED = "note_added"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Build the PostgreSQL ENUM type for a Python enum."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        native_enum=True,
        create_type=False,  # migrations own type creation, not autogenerate
    )


USER_ROLE = pg_enum(UserRole, "user_role")
BOOKING_STATUS = pg_enum(BookingStatus, "booking_status")
BOOKING_EVENT_TYPE = pg_enum(BookingEventType, "booking_event_type")
