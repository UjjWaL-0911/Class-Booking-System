"""ORM models.

Every model is imported here so that ``Base.metadata`` is complete by the time
Alembic inspects it. A model that is not imported is invisible to autogenerate,
and the resulting migration would silently drop its table.
"""

from app.db.base import Base
from app.models.booking import Booking, BookingEvent
from app.models.class_session import ClassSession, SessionCoInstructor
from app.models.enums import (
    BOOKING_EVENT_TYPE,
    BOOKING_STATUS,
    USER_ROLE,
    BookingEventType,
    BookingStatus,
    UserRole,
)
from app.models.member import Member, MembershipAlertDismissal
from app.models.room import Room
from app.models.studio_class import StudioClass
from app.models.user import RefreshToken, User

__all__ = [
    "BOOKING_EVENT_TYPE",
    "BOOKING_STATUS",
    "USER_ROLE",
    "Base",
    "Booking",
    "BookingEvent",
    "BookingEventType",
    "BookingStatus",
    "ClassSession",
    "Member",
    "MembershipAlertDismissal",
    "RefreshToken",
    "Room",
    "SessionCoInstructor",
    "StudioClass",
    "User",
    "UserRole",
]
