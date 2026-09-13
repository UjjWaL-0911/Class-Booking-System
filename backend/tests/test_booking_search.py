"""Bookings list tests (goal 6).

Goal 6 ends with an instruction rather than a feature: "All of this must happen on
the server — do not load every booking into the browser and filter there." So these
tests assert on what the *server* returned, and in particular that `total` reflects
the whole filtered set rather than the page — a client-side filter would make the
two agree trivially and prove nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")

FUTURE = dt.date(2027, 9, 7)


async def _room(staff: AsyncClient) -> str:
    r = await staff.post("/api/v1/rooms", json={"name": f"S {uuid.uuid4().hex[:8]}"})
    return str(r.json()["id"])


async def _class(staff: AsyncClient, title: str | None = None) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/classes",
        json={
            "title": title or f"Class {uuid.uuid4().hex[:6]}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": 20,
        },
    )
    return dict(r.json())


async def _user_id(db: AsyncSession, email: str) -> str:
    return str(
        (await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})).scalar_one()
    )


async def _session(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    *,
    class_id: str | None = None,
    capacity: int = 20,
    at: str = "18:00:00",
    on: dt.date | None = None,
    instructor_id: str | None = None,
) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": class_id or (await _class(staff))["id"],
            "session_date": (on or FUTURE).isoformat(),
            "start_time": at,
            "primary_instructor_id": instructor_id or await _user_id(db, accounts["instructor"]),
            "room_id": await _room(staff),
            "capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _member(staff: AsyncClient, name: str | None = None) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    r = await staff.post(
        "/api/v1/members",
        json={
            "full_name": name or f"Member {tag}",
            "email": f"m-{tag}@example.com",
            "membership_expiry": "2030-01-01",
            "notes": "",
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _book(staff: AsyncClient, session_id: str, member_id: str) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/bookings", json={"session_id": session_id, "member_id": member_id}
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


class TestSearch:
    async def test_search_matches_member_name(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        tag = uuid.uuid4().hex[:8]
        wanted = await _member(staff, name=f"Katherine {tag}")
        await _book(staff, session["id"], wanted["id"])
        await _book(staff, session["id"], (await _member(staff))["id"])

        body = (await staff.get(f"/api/v1/bookings?q={tag}")).json()

        assert body["total"] == 1
        assert body["items"][0]["member_name"] == f"Katherine {tag}"

    async def test_search_matches_member_email(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The citext cast in the query is what makes this use the trigram index
        rather than sequentially scanning members."""
        session = await _session(staff, db, accounts)
        member = await _member(staff)
        await _book(staff, session["id"], member["id"])
        local = member["email"].split("@")[0]

        body = (await staff.get(f"/api/v1/bookings?q={local}")).json()

        assert body["total"] == 1
        assert body["items"][0]["member_email"] == member["email"]

    async def test_search_is_case_insensitive(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        tag = uuid.uuid4().hex[:8]
        await _book(staff, session["id"], (await _member(staff, name=f"Dorothy {tag}"))["id"])

        body = (await staff.get(f"/api/v1/bookings?q={tag.upper()}")).json()

        assert body["total"] == 1


class TestFilters:
    async def test_filter_by_status(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=1)
        first = await _book(staff, session["id"], (await _member(staff))["id"])
        await _book(staff, session["id"], (await _member(staff))["id"])
        await staff.post(f"/api/v1/bookings/{first['id']}/cancel", json={})

        scope = f"session_id={session['id']}"
        waitlisted = (await staff.get(f"/api/v1/bookings?{scope}&status=waitlisted")).json()
        cancelled = (await staff.get(f"/api/v1/bookings?{scope}&status=cancelled")).json()

        # The waitlisted member was promoted when the booked one cancelled, so
        # there is nothing left waiting — which is goal 4 working, visible here.
        assert waitlisted["total"] == 0
        assert cancelled["total"] == 1

    async def test_filter_by_session(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        wanted = await _session(staff, db, accounts, at="09:00:00")
        other = await _session(staff, db, accounts, at="11:00:00")
        await _book(staff, wanted["id"], (await _member(staff))["id"])
        await _book(staff, other["id"], (await _member(staff))["id"])

        body = (await staff.get(f"/api/v1/bookings?session_id={wanted['id']}")).json()

        assert body["total"] == 1
        assert body["items"][0]["session_id"] == wanted["id"]

    async def test_filter_by_class(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        first = await _session(staff, db, accounts, class_id=studio_class["id"], at="09:00:00")
        second = await _session(staff, db, accounts, class_id=studio_class["id"], at="11:00:00")
        other = await _session(staff, db, accounts, at="13:00:00")
        await _book(staff, first["id"], (await _member(staff))["id"])
        await _book(staff, second["id"], (await _member(staff))["id"])
        await _book(staff, other["id"], (await _member(staff))["id"])

        body = (await staff.get(f"/api/v1/bookings?class_id={studio_class['id']}")).json()

        assert body["total"] == 2
        assert {i["class_id"] for i in body["items"]} == {studio_class["id"]}

    async def test_filters_combine(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        studio_class = await _class(staff)
        session = await _session(staff, db, accounts, class_id=studio_class["id"])
        tag = uuid.uuid4().hex[:8]
        await _book(staff, session["id"], (await _member(staff, name=f"Ada {tag}"))["id"])
        await _book(staff, session["id"], (await _member(staff))["id"])

        body = (
            await staff.get(f"/api/v1/bookings?class_id={studio_class['id']}&status=booked&q={tag}")
        ).json()

        assert body["total"] == 1


class TestSorting:
    async def test_sort_by_booked_time(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        first = await _book(staff, session["id"], (await _member(staff))["id"])
        second = await _book(staff, session["id"], (await _member(staff))["id"])

        scope = f"session_id={session['id']}"
        asc = (await staff.get(f"/api/v1/bookings?{scope}&sort=booked_at&direction=asc")).json()
        desc = (await staff.get(f"/api/v1/bookings?{scope}&sort=booked_at&direction=desc")).json()

        assert [i["id"] for i in asc["items"]] == [first["id"], second["id"]]
        assert [i["id"] for i in desc["items"]] == [second["id"], first["id"]]

    async def test_sort_by_session_is_chronological(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """ "Sorting by session" means by start time, not by id — which is what a
        person reading a schedule expects, and needs a join to the sessions table
        that no index on bookings can serve."""
        studio_class = await _class(staff)
        later = await _session(staff, db, accounts, class_id=studio_class["id"], at="17:00:00")
        earlier = await _session(staff, db, accounts, class_id=studio_class["id"], at="08:00:00")
        await _book(staff, later["id"], (await _member(staff))["id"])
        await _book(staff, earlier["id"], (await _member(staff))["id"])

        body = (
            await staff.get(
                f"/api/v1/bookings?class_id={studio_class['id']}&sort=session&direction=asc"
            )
        ).json()

        assert [i["session_id"] for i in body["items"]] == [
            earlier["id"],
            later["id"],
        ]

    async def test_sort_by_status(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=1)
        await _book(staff, session["id"], (await _member(staff))["id"])
        await _book(staff, session["id"], (await _member(staff))["id"])

        body = (
            await staff.get(
                f"/api/v1/bookings?session_id={session['id']}&sort=status&direction=asc"
            )
        ).json()

        statuses = [i["status"] for i in body["items"]]
        assert statuses == sorted(statuses)

    async def test_ordering_is_stable_across_identical_keys(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Every sort carries booking id as a tiebreak. Without it, rows with equal
        keys can swap between requests, and a client paging through would see one
        booking twice and another not at all."""
        session = await _session(staff, db, accounts, capacity=10)
        for _ in range(6):
            await _book(staff, session["id"], (await _member(staff))["id"])

        scope = f"session_id={session['id']}&sort=status"
        first = (await staff.get(f"/api/v1/bookings?{scope}")).json()
        again = (await staff.get(f"/api/v1/bookings?{scope}")).json()

        assert [i["id"] for i in first["items"]] == [i["id"] for i in again["items"]]


class TestPagination:
    async def test_total_is_the_filtered_set_not_the_page(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 6: "pagination showing the total number of matches". The count comes
        from count(*) OVER () in the same statement, so it cannot disagree with the
        rows beside it."""
        session = await _session(staff, db, accounts, capacity=10)
        for _ in range(7):
            await _book(staff, session["id"], (await _member(staff))["id"])

        body = (await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=3")).json()

        assert len(body["items"]) == 3
        assert body["total"] == 7

    async def test_paging_covers_the_set_without_overlap(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=10)
        for _ in range(5):
            await _book(staff, session["id"], (await _member(staff))["id"])

        scope = f"session_id={session['id']}&sort=booked_at&direction=asc"
        page_one = (await staff.get(f"/api/v1/bookings?{scope}&limit=2&offset=0")).json()
        page_two = (await staff.get(f"/api/v1/bookings?{scope}&limit=2&offset=2")).json()
        page_three = (await staff.get(f"/api/v1/bookings?{scope}&limit=2&offset=4")).json()

        ids = (
            [i["id"] for i in page_one["items"]]
            + [i["id"] for i in page_two["items"]]
            + [i["id"] for i in page_three["items"]]
        )
        assert len(ids) == 5
        assert len(set(ids)) == 5

    async def test_an_empty_result_reports_zero(self, staff: AsyncClient) -> None:
        """No rows means no window to count over, so the total is zero by
        construction rather than by reading it off a row that is not there."""
        body = (await staff.get("/api/v1/bookings?q=zzz-nobody-zzz")).json()

        assert body["total"] == 0
        assert body["items"] == []

    async def test_the_page_size_is_capped(self, staff: AsyncClient) -> None:
        assert (await staff.get("/api/v1/bookings?limit=100000")).status_code == 422


class TestVisibility:
    async def test_an_instructor_sees_only_bookings_on_their_own_sessions(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """Goal 6 scopes the list to "every session the viewer can see", and goal 1
        requires that to be enforced on the server. The filter is composed into the
        SQL, so the rows are never selected — not fetched and then hidden."""
        other = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :e, 'x', 'Other', 'instructor')"
            ),
            {"id": other, "e": f"other-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.commit()

        mine = await _session(staff, db, accounts, at="09:00:00")
        theirs = await _session(staff, db, accounts, at="11:00:00", instructor_id=str(other))
        my_booking = await _book(staff, mine["id"], (await _member(staff))["id"])
        their_booking = await _book(staff, theirs["id"], (await _member(staff))["id"])

        visible = (await instructor.get("/api/v1/bookings?limit=200")).json()
        ids = [i["id"] for i in visible["items"]]

        assert my_booking["id"] in ids
        assert their_booking["id"] not in ids

    async def test_the_total_respects_visibility(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """A total computed before the visibility filter would leak how many
        bookings exist on sessions the instructor cannot see."""
        other = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :e, 'x', 'Other', 'instructor')"
            ),
            {"id": other, "e": f"other-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.commit()
        theirs = await _session(staff, db, accounts, at="15:00:00", instructor_id=str(other))
        for _ in range(3):
            await _book(staff, theirs["id"], (await _member(staff))["id"])

        body = (await instructor.get(f"/api/v1/bookings?session_id={theirs['id']}")).json()

        assert body["total"] == 0
        assert body["items"] == []


class TestRowShape:
    async def test_a_row_carries_member_session_and_class_together(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """One join, one round trip. The alternative — ids the client resolves with
        follow-up requests — is the N+1 this query exists to avoid."""
        studio_class = await _class(staff, title=f"Vinyasa {uuid.uuid4().hex[:6]}")
        session = await _session(staff, db, accounts, class_id=studio_class["id"])
        member = await _member(staff)
        booking = await _book(staff, session["id"], member["id"])

        item = (await staff.get(f"/api/v1/bookings?session_id={session['id']}")).json()["items"][0]

        assert item["id"] == booking["id"]
        assert item["member_name"] == member["full_name"]
        assert item["member_email"] == member["email"]
        assert item["class_title"] == studio_class["title"]
        assert item["discipline"] == studio_class["discipline"]
        assert item["session_date"] == FUTURE.isoformat()
        assert item["session_has_passed"] is False


class TestDateRange:
    """Bounding the list by class date (goal 6's filters).

    The range is over the *session's* date rather than over when the booking was
    taken — "what is on next week, and who is coming" is the question a desk
    asks. It is also what `date_from` and `date_to` already mean on the sessions
    endpoint, and one word meaning two things across one API is how a client ends
    up quietly filtering the wrong column.

    Every case here creates its own class and filters by it. That is not tidiness:
    the suite shares one database and never truncates — `booking_events` rejects
    it by design — and the schema survives between runs, so an unscoped range
    counts the previous run's rows as well as this one's. The first draft of these
    tests passed once and then failed on the second run, which is the most
    annoying way to learn it.

    Assertions are on `total` as well as the rows, because goal 6 forbids
    filtering in the browser and a client-side filter would make the page look
    right while the total gave it away.
    """

    async def test_a_range_excludes_what_falls_outside_it(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        only = await _class(staff, title="Range Excludes")
        early = await _session(staff, db, accounts, class_id=only["id"], on=dt.date(2027, 3, 1))
        inside = await _session(staff, db, accounts, class_id=only["id"], on=dt.date(2027, 3, 10))
        late = await _session(staff, db, accounts, class_id=only["id"], on=dt.date(2027, 3, 20))
        for session in (early, inside, late):
            await _book(staff, session["id"], (await _member(staff))["id"])

        body = (
            await staff.get(
                "/api/v1/bookings",
                params={
                    "class_id": only["id"],
                    "date_from": "2027-03-05",
                    "date_to": "2027-03-15",
                },
            )
        ).json()

        assert body["total"] == 1
        assert [row["session_id"] for row in body["items"]] == [inside["id"]]

    async def test_both_ends_are_inclusive(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A range somebody typed includes both days they typed.

        The end is the one that goes wrong: comparing against midnight on
        `date_to` silently drops everything after 00:00 that day, which is the
        whole day. The 23:30 class is what catches that.
        """
        only = await _class(staff, title="Range Inclusive")
        first = await _session(
            staff, db, accounts, class_id=only["id"], on=dt.date(2027, 4, 5), at="06:00:00"
        )
        last = await _session(
            staff, db, accounts, class_id=only["id"], on=dt.date(2027, 4, 9), at="23:30:00"
        )
        for session in (first, last):
            await _book(staff, session["id"], (await _member(staff))["id"])

        body = (
            await staff.get(
                "/api/v1/bookings",
                params={
                    "class_id": only["id"],
                    "date_from": "2027-04-05",
                    "date_to": "2027-04-09",
                },
            )
        ).json()

        assert body["total"] == 2
        assert {row["session_id"] for row in body["items"]} == {first["id"], last["id"]}

    async def test_the_boundary_is_the_studio_day_not_the_utc_day(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The studio is at +05:30, so a class at half past midnight local is the
        *previous* day in UTC. Filtering by the calendar the studio actually uses
        has to include it; filtering on the stored instant's UTC date would not,
        and the failure would look like one booking missing from a week for no
        reason anybody could see.
        """
        only = await _class(staff, title="Range Midnight")
        after_midnight = await _session(
            staff, db, accounts, class_id=only["id"], on=dt.date(2027, 5, 3), at="00:30:00"
        )
        await _book(staff, after_midnight["id"], (await _member(staff))["id"])

        inside = (
            await staff.get(
                "/api/v1/bookings",
                params={
                    "class_id": only["id"],
                    "date_from": "2027-05-03",
                    "date_to": "2027-05-03",
                },
            )
        ).json()
        assert inside["total"] == 1

        # And not on the day before, which is where UTC would have filed it.
        outside = (
            await staff.get(
                "/api/v1/bookings",
                params={
                    "class_id": only["id"],
                    "date_from": "2027-05-02",
                    "date_to": "2027-05-02",
                },
            )
        ).json()
        assert outside["total"] == 0

    async def test_one_end_alone_is_an_open_range(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        only = await _class(staff, title="Range Open")
        before = await _session(staff, db, accounts, class_id=only["id"], on=dt.date(2027, 6, 1))
        after = await _session(staff, db, accounts, class_id=only["id"], on=dt.date(2027, 6, 30))
        for session in (before, after):
            await _book(staff, session["id"], (await _member(staff))["id"])

        from_only = (
            await staff.get(
                "/api/v1/bookings", params={"class_id": only["id"], "date_from": "2027-06-15"}
            )
        ).json()
        assert [row["session_id"] for row in from_only["items"]] == [after["id"]]

        to_only = (
            await staff.get(
                "/api/v1/bookings", params={"class_id": only["id"], "date_to": "2027-06-15"}
            )
        ).json()
        assert [row["session_id"] for row in to_only["items"]] == [before["id"]]

    async def test_the_range_narrows_the_other_filters(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Filters compose: a class and a range together mean both, and `total`
        counts the intersection rather than either one alone."""
        wanted = await _class(staff, title="Range Combined")
        inside = await _session(staff, db, accounts, class_id=wanted["id"], on=dt.date(2027, 7, 10))
        outside = await _session(
            staff, db, accounts, class_id=wanted["id"], on=dt.date(2027, 8, 10)
        )
        elsewhere = await _session(staff, db, accounts, on=dt.date(2027, 7, 11))
        for session in (inside, outside, elsewhere):
            await _book(staff, session["id"], (await _member(staff))["id"])

        body = (
            await staff.get(
                "/api/v1/bookings",
                params={
                    "class_id": wanted["id"],
                    "date_from": "2027-07-01",
                    "date_to": "2027-07-31",
                },
            )
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["session_id"] == inside["id"]

    async def test_a_backwards_range_finds_nothing_rather_than_erroring(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """An end before a start is an empty range, not a bad request. A form can
        hold that state for a keystroke while somebody retypes a month, and a 422
        mid-typing is worse than an empty list."""
        only = await _class(staff, title="Range Backwards")
        session = await _session(staff, db, accounts, class_id=only["id"], on=dt.date(2027, 9, 15))
        await _book(staff, session["id"], (await _member(staff))["id"])

        response = await staff.get(
            "/api/v1/bookings",
            params={
                "class_id": only["id"],
                "date_from": "2027-09-20",
                "date_to": "2027-09-10",
            },
        )

        assert response.status_code == 200
        assert response.json()["total"] == 0

class TestWaitlistPosition:
    """Where a member is in the queue (the "waitlist position" stretch idea).

    Members have no accounts in this system, so "visibility for members" means the
    person at the front desk can answer "where am I?" without opening the session
    and counting. The number therefore appears wherever a booking is looked up: the
    bookings list and the booking's own history.

    The property that actually matters is the last test here — the number has to
    agree with who the system would really promote next. A position computed from a
    different ordering would never fail; it would just tell somebody they are third
    when they are fourth, and nobody finds out until a seat frees.
    """

    async def _queue(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str], waiting: int = 3
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """A session with one seat, filled, and `waiting` people behind it."""
        session = await _session(staff, db, accounts, capacity=1)
        members = []
        for _ in range(waiting + 1):
            member = await _member(staff)
            await _book(staff, session["id"], member["id"])
            members.append(member)
        return session, members

    async def test_the_queue_is_numbered_from_one(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session, members = await self._queue(staff, db, accounts)

        rows = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")
        ).json()["items"]
        by_member = {r["member_id"]: r for r in rows}

        # The first to book got the seat, so they have no position at all.
        assert by_member[members[0]["id"]]["status"] == "booked"
        assert by_member[members[0]["id"]]["waitlist_position"] is None

        for place, member in enumerate(members[1:], start=1):
            row = by_member[member["id"]]
            assert row["status"] == "waitlisted"
            assert row["waitlist_position"] == place

    async def test_only_waitlisted_bookings_carry_one(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A cancelled or settled booking is not in any queue, and saying it is
        third would be worse than saying nothing."""
        session, _members = await self._queue(staff, db, accounts, waiting=1)
        waiting = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&status=waitlisted")
        ).json()["items"][0]

        await staff.post(f"/api/v1/bookings/{waiting['id']}/cancel", json={"note": None})

        after = (await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")).json()
        cancelled = next(r for r in after["items"] if r["id"] == waiting["id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["waitlist_position"] is None

    async def test_cancelling_someone_ahead_moves_everyone_up(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session, members = await self._queue(staff, db, accounts, waiting=3)

        rows = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")
        ).json()["items"]
        second = next(
            r for r in rows if r["member_id"] == members[2]["id"]
        )  # third to book, second in the queue
        assert second["waitlist_position"] == 2

        first_waiting = next(r for r in rows if r["member_id"] == members[1]["id"])
        await staff.post(f"/api/v1/bookings/{first_waiting['id']}/cancel", json={"note": None})

        moved = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")
        ).json()["items"]
        assert next(r for r in moved if r["member_id"] == members[2]["id"])[
            "waitlist_position"
        ] == 1

    async def test_the_position_appears_on_the_bookings_history(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session, members = await self._queue(staff, db, accounts, waiting=2)
        rows = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")
        ).json()["items"]
        last = next(r for r in rows if r["member_id"] == members[2]["id"])

        timeline = (await staff.get(f"/api/v1/bookings/{last['id']}/timeline")).json()

        assert timeline["status"] == "waitlisted"
        assert timeline["waitlist_position"] == 2

    async def test_a_booked_booking_has_no_position_on_its_history(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session, _members = await self._queue(staff, db, accounts, waiting=1)
        rows = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")
        ).json()["items"]
        booked = next(r for r in rows if r["status"] == "booked")

        timeline = (await staff.get(f"/api/v1/bookings/{booked['id']}/timeline")).json()

        assert timeline["waitlist_position"] is None

    async def test_position_one_is_who_actually_gets_promoted(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """The whole point. The number is only useful if it agrees with the
        promotion order, so this asserts them against each other rather than
        asserting each against my own assumption."""
        session, _ = await self._queue(staff, db, accounts, waiting=3)
        rows = (
            await staff.get(f"/api/v1/bookings?session_id={session['id']}&limit=50")
        ).json()["items"]
        next_up = next(r for r in rows if r["waitlist_position"] == 1)
        booked = next(r for r in rows if r["status"] == "booked")

        result = (
            await staff.post(f"/api/v1/bookings/{booked['id']}/cancel", json={"note": None})
        ).json()

        assert result["promoted"] is not None
        assert result["promoted"]["id"] == next_up["id"]
