"""Populate a database with the demo studio.

The brief asks for "enough demo data to show the system doing something, not an
empty shell", and the important word is *doing*. So this drives the real services
rather than inserting rows: every booking goes through the state machine, every
waitlist is produced by a session genuinely filling up, and every promotion is a
real cancellation being processed. The audit timelines a reviewer opens are the
system's own, not fixtures shaped to look like them.

History is made honestly rather than by editing rows. The services take ``now`` as
a parameter — which exists so tests can control the clock — so a booking on a class
that happened six weeks ago is created with ``now`` set to a week before that class,
and settled with ``now`` set to just after it ended. Every guard is satisfied for
real: the session had not started when the booking was made, and had finished when
attendance was recorded.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.core.time import to_utc
from app.models.booking import Booking
from app.models.class_session import ClassSession, SessionCoInstructor
from app.models.enums import BookingStatus, UserRole
from app.models.member import Member, MembershipAlertDismissal
from app.models.room import Room
from app.models.studio_class import StudioClass
from app.models.user import User
from app.seed import data
from app.services.booking_service import BookingService

# Fixed so two runs of the seed produce the same studio. A demo that differs every
# time is one you cannot write documentation against.
RNG_SEED = 20260914


@dataclass
class SeedSummary:
    users: int = 0
    rooms: int = 0
    classes: int = 0
    sessions: int = 0
    co_instructors: int = 0
    members: int = 0
    member_logins: int = 0
    bookings: int = 0
    waitlisted: int = 0
    cancelled: int = 0
    settled: int = 0
    notes: list[str] = field(default_factory=list)


class Seeder:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.rng = random.Random(RNG_SEED)  # noqa: S311 — demo data, not crypto
        self.now = dt.datetime.now(dt.UTC)
        self.today = self.now.astimezone(settings.tz).date()
        self.summary = SeedSummary()

        self.users: dict[str, User] = {}
        self.rooms: dict[str, Room] = {}
        self.classes: dict[str, StudioClass] = {}
        self.members: list[Member] = []

    async def run(self) -> SeedSummary:
        await self._people()
        await self._studio()
        await self._timetable()
        await self._co_instructors()
        await self._bookings()
        await self._dismissal()
        await self.db.commit()
        return self.summary

    # --------------------------------------------------------------- people

    async def _people(self) -> None:
        digest = await hash_password(data.DEMO_PASSWORD, self.settings)
        for seed_user in [*data.STAFF, *data.INSTRUCTORS]:
            user = User(
                email=seed_user.email,
                password_hash=digest,
                full_name=seed_user.full_name,
                role=seed_user.role,
                session_rate_minor=seed_user.session_rate_minor,
            )
            self.db.add(user)
            self.users[seed_user.email] = user
            self.summary.users += 1

        for seed_member in data.MEMBERS:
            member = Member(
                full_name=seed_member.full_name,
                email=seed_member.email,
                membership_expiry=self.today + dt.timedelta(days=seed_member.expiry_offset_days),
                notes="",
            )
            # A login, for the two members the demo needs to be able to sign in.
            # Created exactly the way the endpoint creates one — a users row with
            # role='member', linked from members.user_id — rather than by writing
            # the columns directly, so the seed cannot drift from the feature.
            if seed_member.self_service:
                account = User(
                    email=seed_member.email,
                    full_name=seed_member.full_name,
                    role=UserRole.MEMBER,
                    password_hash=digest,
                )
                self.db.add(account)
                await self.db.flush()
                member.user_id = account.id
                self.summary.member_logins += 1

            self.db.add(member)
            self.members.append(member)
            self.summary.members += 1

        await self.db.flush()

    async def _studio(self) -> None:
        for name in data.ROOMS:
            room = Room(name=name)
            self.db.add(room)
            self.rooms[name] = room
            self.summary.rooms += 1

        for seed_class in data.CLASSES:
            studio_class = StudioClass(
                title=seed_class.title,
                discipline=seed_class.discipline,
                description=seed_class.description,
                default_duration_min=seed_class.duration_min,
                default_capacity=seed_class.capacity,
                archived_at=self.now if seed_class.archived else None,
            )
            self.db.add(studio_class)
            self.classes[seed_class.title] = studio_class
            self.summary.classes += 1

        await self.db.flush()

    # ------------------------------------------------------------ timetable

    async def _timetable(self) -> None:
        """Generate the weekly timetable across the whole window.

        Eight weeks back and three ahead. The history is what gives the dashboard's
        attendance chart something to draw and makes "no-shows this week" a real
        number rather than a zero.
        """
        monday = self.today - dt.timedelta(days=self.today.weekday())
        start = monday - dt.timedelta(weeks=data.WEEKS_OF_HISTORY)
        end = monday + dt.timedelta(weeks=data.WEEKS_AHEAD)

        day = start
        while day <= end:
            for slot in data.TIMETABLE:
                if day.weekday() != slot.weekday:
                    continue
                studio_class = self.classes[slot.class_title]
                if studio_class.archived_at is not None:
                    continue
                try:
                    starts_at = to_utc(day, slot.start, self.settings.tz)
                except ValueError:
                    # A local time that does not exist because the clocks changed.
                    continue
                self.db.add(
                    ClassSession(
                        class_id=studio_class.id,
                        starts_at=starts_at,
                        primary_instructor_id=self.users[slot.instructor_email].id,
                        room_id=self.rooms[slot.room].id,
                        duration_min=studio_class.default_duration_min,
                        capacity=studio_class.default_capacity,
                    )
                )
                self.summary.sessions += 1
            day += dt.timedelta(days=1)

        await self.db.flush()

    # -------------------------------------------------------- co-instructors

    async def _co_instructors(self) -> None:
        """Put a second instructor on some sessions (goal 5).

        Chosen so the relationship is demonstrable rather than merely present: each
        co-instructor is someone other than the session's primary, which is what
        makes the visibility rule visible — that instructor can now see a session
        they do not lead, and loses it again if they are removed.

        No overlap check, deliberately. Goal 5 allows one instructor to be added to
        any number of sessions including simultaneous ones, which is why the
        exclusion constraint covers only the primary instructor.
        """
        sessions = (await self.db.execute(select(ClassSession))).scalars().all()
        instructors = [self.users[u.email] for u in data.INSTRUCTORS]
        added_by = self.users["manager@studio.demo"]

        wanted = round(len(sessions) * data.CO_INSTRUCTOR_SHARE)
        for session in self.rng.sample(list(sessions), min(wanted, len(sessions))):
            candidates = [i for i in instructors if i.id != session.primary_instructor_id]
            if not candidates:
                continue
            self.db.add(
                SessionCoInstructor(
                    session_id=session.id,
                    user_id=self.rng.choice(candidates).id,
                    added_by=added_by.id,
                    added_at=self.now,
                )
            )
            self.summary.co_instructors += 1

        await self.db.flush()

    # ------------------------------------------------------------- bookings

    async def _bookings(self) -> None:
        sessions = (
            (await self.db.execute(select(ClassSession).order_by(ClassSession.starts_at)))
            .scalars()
            .all()
        )
        staff = self.users["manager@studio.demo"]
        service = BookingService(self.db, self.settings)

        past_session_ids: list[tuple[ClassSession, dt.datetime]] = []

        for session in sessions:
            # Each booking is made at a plausible moment before its class, and the
            # services are given that moment as `now`. Every guard is then satisfied
            # for real rather than bypassed.
            # Never later than now: a booking recorded in the future is nonsense,
            # and it would also make "bookings made today" permanently zero, since
            # every booking for a distant class would be stamped after today.
            booked_on = min(
                session.starts_at - dt.timedelta(days=self.rng.randint(1, 10)),
                self.now - dt.timedelta(minutes=self.rng.randint(0, 600)),
            )

            # Eligibility is judged against the booking date, not today. A member
            # whose membership lapses next week cannot be booked onto a class the
            # week after — which is goal 4 working, and the seed has to respect it
            # rather than route around it.
            as_of = booked_on.astimezone(self.settings.tz).date()
            eligible = [m for m in self.members if m.membership_expiry >= as_of]
            if not eligible:
                continue

            # Popular classes fill and spill onto the waitlist; quiet ones do not.
            demand = self.rng.choice([0.4, 0.7, 1.0, 1.3])
            wanted = max(1, round(session.capacity * demand))
            attendees = self.rng.sample(eligible, min(wanted, len(eligible)))

            for member in attendees:
                booking = await service.create(
                    session_id=session.id,
                    member_id=member.id,
                    actor=staff,
                    now=booked_on,
                )
                if booking.status is BookingStatus.WAITLISTED:
                    self.summary.waitlisted += 1
                else:
                    self.summary.bookings += 1

            if session.starts_at < self.now:
                past_session_ids.append((session, session.starts_at))

        await self._cancellations(service, staff)
        await self._settle_history(service, staff, past_session_ids)

    async def _cancellations(self, service: BookingService, staff: User) -> None:
        """Cancel a handful of future bookings, so the waitlist visibly works.

        Each cancellation that frees a seat promotes someone, and that promotion is
        recorded as a system action in the timeline — which is the single most
        interesting thing to click into in the demo.
        """
        # Drawn from sessions that actually have a waitlist, so cancelling frees a
        # seat someone is waiting for. Cancelling a booking on a half-empty class
        # is a valid thing to demonstrate but a dull one — nothing happens.
        waitlisted_sessions = (
            select(Booking.session_id)
            .where(Booking.status == BookingStatus.WAITLISTED)
            .distinct()
            .scalar_subquery()
        )
        candidates = (
            (
                await self.db.execute(
                    select(Booking)
                    .join(ClassSession, ClassSession.id == Booking.session_id)
                    .where(
                        Booking.status == BookingStatus.BOOKED,
                        ClassSession.starts_at > self.now,
                        Booking.session_id.in_(waitlisted_sessions),
                    )
                    .order_by(Booking.booked_at)
                )
            )
            .scalars()
            .all()
        )
        for booking in self.rng.sample(list(candidates), min(18, len(candidates))):
            # Somewhere between the booking being taken and now — not a fixed
            # window before now, which was the bug here. A booking for a distant
            # class is stamped within the last few hours (see `booked_on` above),
            # so "one to seventy-two hours ago" could land *before* the booking it
            # cancels, and goal 9's timeline then read as undoing something that
            # had not happened yet. The one screen a reviewer opens to check the
            # audit trail is the worst place to have the clock run backwards.
            cancelled_on = booking.booked_at + (self.now - booking.booked_at) * self.rng.random()
            _, promoted = await service.cancel(
                booking.id,
                actor=staff,
                now=cancelled_on,
                note=self.rng.choice(
                    [
                        "Member called to cancel.",
                        "Travelling this week.",
                        "Injury — will rebook.",
                        None,
                    ]
                ),
            )
            self.summary.cancelled += 1
            if promoted is not None:
                self.summary.notes.append(
                    f"Waitlist promotion recorded on session {promoted.session_id}"
                )

    async def _settle_history(
        self,
        service: BookingService,
        staff: User,
        past: list[tuple[ClassSession, dt.datetime]],
    ) -> None:
        """Mark attendance on everything that has already happened.

        Without this the dashboard's eight-week chart is empty and "no-shows this
        week" is always zero — the two figures that need history to mean anything.
        """
        for session, starts_at in past:
            bookings = (
                (
                    await self.db.execute(
                        select(Booking).where(
                            Booking.session_id == session.id,
                            Booking.status == BookingStatus.BOOKED,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for booking in bookings:
                # Roughly one in eight does not turn up, which is a believable
                # no-show rate and enough to make the chart non-trivial.
                attended = self.rng.random() > 0.125
                await service.settle(
                    booking.id,
                    attended=attended,
                    actor=staff,
                    now=starts_at + dt.timedelta(minutes=session.duration_min),
                )
                self.summary.settled += 1

    # -------------------------------------------------------------- alerts

    async def _dismissal(self) -> None:
        """Dismiss one alert, so the demo shows suppression as well as the feed."""
        member = next((m for m in self.members if m.email == data.DISMISSED_ALERT_FOR), None)
        if member is None:
            return
        self.db.add(
            MembershipAlertDismissal(
                member_id=member.id,
                dismissed_expiry=member.membership_expiry,
                dismissed_by=self.users["frontdesk@studio.demo"].id,
                dismissed_at=self.now,
            )
        )
        self.summary.notes.append(
            f"Alert dismissed for {member.full_name} — will return if the expiry moves"
        )


async def is_seeded(db: AsyncSession) -> bool:
    """Whether this database already holds the demo studio.

    Keyed on the demo domain rather than on "are there any users at all", so it
    cannot mistake a real deployment's first staff account for demo data.
    """
    count: int = (
        await db.execute(text("SELECT count(*) FROM users WHERE email LIKE '%@studio.demo'"))
    ).scalar_one()
    return count > 0
