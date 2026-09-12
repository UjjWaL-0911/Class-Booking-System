"""The demo studio.

Literal content only — no logic. Kept separate so the seeding *procedure* can be
read without wading through names, and so the studio can be re-imagined without
touching anything that talks to the database.

The shape of this data is chosen to make the system demonstrate itself: there are
memberships expiring this week and memberships that lapsed months ago (goal 10),
classes at capacity so the waitlist is populated (goal 4), an archived class (goal
2), and eight weeks of settled history so the dashboard chart is not a flat line
(goal 8).
"""

from __future__ import annotations

import datetime as dt
from typing import NamedTuple

from app.models.enums import UserRole

# One password for every demo account. A real deployment would not do this; a demo
# whose credentials a reviewer has to keep looking up is worse than one that is
# obviously a demo.
# Flagged by the linter as a hardcoded password, and suppressed deliberately:
# it is demo-account content, published in SUBMISSION.md on purpose, and the
# seed refuses to run against a production environment.
DEMO_PASSWORD = "StudioDemo!2026"  # noqa: S105


class SeedUser(NamedTuple):
    email: str
    full_name: str
    role: UserRole


class SeedClass(NamedTuple):
    title: str
    discipline: str
    description: str
    duration_min: int
    capacity: int
    archived: bool = False


class Slot(NamedTuple):
    """One entry in the weekly timetable."""

    weekday: int  # Monday is 0
    start: dt.time
    class_title: str
    room: str
    instructor_email: str


# Two accounts demonstrate the role difference, and those two are the ones a
# reviewer signs in with: `manager@` sees the whole studio, `aryan@` sees only the
# classes they teach. Both the address and the name are kept in step on those two,
# because an instructor called Aryan signing in as `priya@` is a puzzle on the
# sign-in screen before it is anything else.
#
# `marcus@` and `elena@` are historical and no longer echo their holder's name.
# They are left alone on purpose: nothing points a reviewer at them, they are not
# printed anywhere, and renaming a login for tidiness is how a demo's credentials
# stop matching the ones written down. `manager@` and `frontdesk@` name a desk
# rather than a person, so they read correctly whoever is sitting at them.
#
# Everyone else keeps a distinct name. A studio with two people called the same
# thing is a studio where you cannot tell which of them taught the class.
#
# Changing an address here means changing it in three other places, none of which
# the type checker will catch: the sign-in page's demo panel, the landing page's
# credentials list, and the summary this package prints when it finishes.
STAFF = [
    SeedUser("manager@studio.demo", "Ujjwal Khanna", UserRole.STAFF),
    SeedUser("frontdesk@studio.demo", "Rohan Iyer", UserRole.STAFF),
]

INSTRUCTORS = [
    SeedUser("aryan@studio.demo", "Aryan Mehta", UserRole.INSTRUCTOR),
    SeedUser("marcus@studio.demo", "Arjun Nair", UserRole.INSTRUCTOR),
    SeedUser("elena@studio.demo", "Kavita Joshi", UserRole.INSTRUCTOR),
]

ROOMS = ["Studio A", "Studio B", "The Loft"]

CLASSES = [
    SeedClass(
        "Vinyasa Flow",
        "yoga",
        "A flowing sequence linking breath to movement. All levels welcome.",
        60,
        18,
    ),
    SeedClass(
        "Power Spin",
        "cycling",
        "Forty-five minutes of interval work on the bike. Bring a towel.",
        45,
        12,
    ),
    SeedClass(
        "Salsa Basics",
        "dance",
        "Partner work from the ground up. No experience or partner needed.",
        75,
        20,
    ),
    SeedClass(
        "Reformer Pilates",
        "pilates",
        "Small-group reformer work focused on control and alignment.",
        55,
        8,
    ),
    SeedClass(
        "Hot Yoga",
        "yoga",
        "Discontinued while the heating is replaced.",
        90,
        16,
        archived=True,
    ),
]

# Deliberately free of overlaps: no room hosts two classes at once and no
# instructor leads two at once, so the exclusion constraints are satisfied by the
# timetable rather than by luck.
TIMETABLE = [
    Slot(0, dt.time(7, 0), "Power Spin", "Studio B", "marcus@studio.demo"),
    Slot(0, dt.time(18, 0), "Vinyasa Flow", "Studio A", "aryan@studio.demo"),
    Slot(1, dt.time(19, 0), "Salsa Basics", "The Loft", "elena@studio.demo"),
    Slot(2, dt.time(7, 0), "Power Spin", "Studio B", "marcus@studio.demo"),
    Slot(2, dt.time(18, 30), "Reformer Pilates", "Studio A", "aryan@studio.demo"),
    Slot(3, dt.time(19, 0), "Salsa Basics", "The Loft", "elena@studio.demo"),
    Slot(4, dt.time(7, 0), "Power Spin", "Studio B", "marcus@studio.demo"),
    Slot(4, dt.time(18, 0), "Vinyasa Flow", "Studio A", "aryan@studio.demo"),
    Slot(5, dt.time(10, 0), "Vinyasa Flow", "Studio A", "aryan@studio.demo"),
    Slot(5, dt.time(12, 0), "Reformer Pilates", "Studio A", "aryan@studio.demo"),
]

WEEKS_OF_HISTORY = 8
WEEKS_AHEAD = 3

# Roughly this share of sessions gets a second instructor alongside the primary.
# Goal 5 is otherwise invisible in the demo: without any co-instructor rows a
# reviewer cannot see that the relationship exists, and — more to the point —
# cannot see it granting an instructor visibility of a session they do not lead.
CO_INSTRUCTOR_SHARE = 0.3


class SeedMember(NamedTuple):
    full_name: str
    email: str
    # Days from today. Negative is already expired; 0-7 lands inside the alert
    # window; larger values are comfortably valid.
    expiry_offset_days: int


# Twenty-two members, running A to V by first name — fabricated on purpose and
# obviously so, which is what a demo roster should look like. The expiry spread is
# chosen so the alerts feed has something in it on the day a reviewer opens the
# link: three already lapsed, four expiring this week, and the rest fine.
MEMBERS = [
    SeedMember("Ananya Iyer", "ananya.iyer@example.com", 210),
    SeedMember("Bhavna Rao", "bhavna.rao@example.com", 95),
    SeedMember("Chirag Patel", "chirag.patel@example.com", -47),
    SeedMember("Divya Menon", "divya.menon@example.com", 3),
    SeedMember("Eshan Ghosh", "eshan.ghosh@example.com", 160),
    SeedMember("Farhan Qureshi", "farhan.qureshi@example.com", 6),
    SeedMember("Gauri Deshmukh", "gauri.deshmukh@example.com", 300),
    SeedMember("Harsh Vora", "harsh.vora@example.com", 44),
    SeedMember("Isha Chawla", "isha.chawla@example.com", -12),
    SeedMember("Jaya Pillai", "jaya.pillai@example.com", 120),
    SeedMember("Kabir Sethi", "kabir.sethi@example.com", 1),
    SeedMember("Lakshmi Nambiar", "lakshmi.nambiar@example.com", 75),
    SeedMember("Manav Bhatia", "manav.bhatia@example.com", 250),
    SeedMember("Nandita Roy", "nandita.roy@example.com", 30),
    SeedMember("Omkar Kulkarni", "omkar.kulkarni@example.com", -3),
    SeedMember("Pooja Reddy", "pooja.reddy@example.com", 185),
    SeedMember("Qamar Sheikh", "qamar.sheikh@example.com", 7),
    SeedMember("Rhea Malhotra", "rhea.malhotra@example.com", 140),
    SeedMember("Siddharth Jain", "siddharth.jain@example.com", 60),
    SeedMember("Tanvi Shetty", "tanvi.shetty@example.com", 330),
    SeedMember("Utkarsh Mishra", "utkarsh.mishra@example.com", 88),
    SeedMember("Vikram Chandra", "vikram.chandra@example.com", 55),
]

# One member whose alert has been dismissed, so the demo shows the suppression
# working as well as the alert itself.
DISMISSED_ALERT_FOR = "qamar.sheikh@example.com"
