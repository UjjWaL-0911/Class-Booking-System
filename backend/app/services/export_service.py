"""Attendance export (goal 7).

"Export a session's attendance — every booking with its member and final status —
as a CSV file."

Every booking, not only the ones that turned up: a register that omitted the
cancellations and absences would not be an attendance record, it would be a
guest list.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking
from app.models.class_session import ClassSession

# A cell starting with any of these is interpreted as a formula by Excel, Google
# Sheets and LibreOffice alike. A member named "=cmd|..." would then execute on
# open. Prefixing with an apostrophe makes the cell literal text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

_HEADERS = (
    "member_name",
    "member_email",
    "status",
    "booked_at",
    "cancelled_at",
    "settled_at",
)


def escape_cell(value: str) -> str:
    """Neutralise spreadsheet formula injection.

    Not paranoia about a hypothetical: the member name is free text typed at a
    front desk, it lands in this file unaltered, and the file is opened in Excel
    by definition. This is the whole distance between a CSV export and a
    remote-code-execution vector.
    """
    if value and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _format_instant(value: dt.datetime | None, tz: ZoneInfo) -> str:
    """Render in the studio's timezone, not UTC.

    A register read at the front desk should show the times staff recognise.
    """
    if value is None:
        return ""
    return value.astimezone(tz).strftime("%Y-%m-%d %H:%M")


class ExportService:
    def __init__(self, db: AsyncSession, tz: ZoneInfo) -> None:
        self.db = db
        self.tz = tz

    async def attendance_csv(self, session: ClassSession) -> str:
        bookings = (
            (
                await self.db.execute(
                    select(Booking)
                    .where(Booking.session_id == session.id)
                    .order_by(Booking.booked_at, Booking.id)
                    .options(selectinload(Booking.member))
                )
            )
            .scalars()
            .all()
        )

        buffer = io.StringIO()
        # Windows line endings: the likeliest consumer is Excel on Windows, and
        # csv.writer would otherwise emit a blank line between rows on its own.
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(_HEADERS)

        for booking in bookings:
            writer.writerow(
                [
                    escape_cell(booking.member.full_name),
                    escape_cell(booking.member.email),
                    booking.status.label,
                    _format_instant(booking.booked_at, self.tz),
                    _format_instant(booking.cancelled_at, self.tz),
                    _format_instant(booking.settled_at, self.tz),
                ]
            )

        return buffer.getvalue()

    @staticmethod
    def filename(session: ClassSession, title: str, tz: ZoneInfo) -> str:
        """A filename that sorts and is safe on every filesystem."""
        local = session.starts_at.astimezone(tz)
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in title).strip("-")
        return f"attendance-{safe}-{local:%Y-%m-%d-%H%M}.csv"
