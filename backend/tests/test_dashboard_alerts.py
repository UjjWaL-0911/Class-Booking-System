"""Dashboard (goal 8) and expiring-membership alerts (goal 10).

Both goals turn on definitions more than on arithmetic. Goal 8 names four figures
but not what they mean at the edges — which day is "today", which week is "this
week", and whether a member waitlisted on a class that already happened is still
"currently waitlisted". Goal 10 spells its edge case out in full, and it is the
last sentence that is the actual requirement.
"""

from __future__ import annotations

import datetime as dt
import itertools
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")


async def _room(staff: AsyncClient) -> str:
    r = await staff.post("/api/v1/rooms", json={"name": f"S {uuid.uuid4().hex[:8]}"})
    return str(r.json()["id"])


async def _class(staff: AsyncClient, **kw: Any) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/classes",
        json={
            "title": f"Class {uuid.uuid4().hex[:6]}",
            "description": "",
            "discipline": "yoga",
            "default_duration_min": 60,
            "default_capacity": 20,
            **kw,
        },
    )
    return dict(r.json())


async def _user_id(db: AsyncSession, email: str) -> str:
    return str(
        (await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})).scalar_one()
    )


async def _member(staff: AsyncClient, *, expiry: str = "2030-01-01") -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    r = await staff.post(
        "/api/v1/members",
        json={
            "full_name": f"Member {tag}",
            "email": f"m-{tag}@example.com",
            "membership_expiry": expiry,
            "notes": "",
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _session_at(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    *,
    day: dt.date,
    at: str = "18:00:00",
    class_id: str | None = None,
    capacity: int = 20,
) -> dict[str, Any]:
    r = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": class_id or (await _class(staff))["id"],
            "session_date": day.isoformat(),
            "start_time": at,
            "primary_instructor_id": await _user_id(db, accounts["instructor"]),
            "room_id": await _room(staff),
            "capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _studio_today(staff: AsyncClient) -> dt.date:
    body = (await staff.get("/api/v1/dashboard")).json()
    return dt.date.fromisoformat(body["as_of"])


class TestHeadlineNumbers:
    async def test_sessions_today_counts_the_studios_today(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """ "Today" is the studio's date, not the server's or the viewer's. A class
        at 23:00 in Kolkata is on the previous UTC day, and counting by UTC would
        quietly drop it from the wrong dashboard."""
        today = await _studio_today(staff)
        before = (await staff.get("/api/v1/dashboard")).json()["headline"]

        await _session_at(staff, db, accounts, day=today, at="23:30:00")
        await _session_at(staff, db, accounts, day=today + dt.timedelta(days=1))

        after = (await staff.get("/api/v1/dashboard")).json()["headline"]
        assert after["sessions_today"] == before["sessions_today"] + 1

    async def test_bookings_today_counts_when_the_booking_was_made(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Not when the class is — a booking made today for next month still
        counts as today's work at the front desk."""
        today = await _studio_today(staff)
        before = (await staff.get("/api/v1/dashboard")).json()["headline"]
        future = await _session_at(staff, db, accounts, day=today + dt.timedelta(days=30))

        await staff.post(
            "/api/v1/bookings",
            json={
                "session_id": future["id"],
                "member_id": (await _member(staff))["id"],
            },
        )

        after = (await staff.get("/api/v1/dashboard")).json()["headline"]
        assert after["bookings_today"] == before["bookings_today"] + 1

    async def test_no_shows_this_week_counts_by_session_date(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Settled today, but the class was weeks ago — so it belongs to that week,
        not this one. Counting by settled_at would move a class into whichever week
        someone got round to the paperwork."""
        today = await _studio_today(staff)
        before = (await staff.get("/api/v1/dashboard")).json()["headline"]

        old = await _session_at(staff, db, accounts, day=today - dt.timedelta(days=30))
        await db.execute(
            text("UPDATE sessions SET starts_at = :t WHERE id = :id"),
            {
                "t": dt.datetime.now(dt.UTC) - dt.timedelta(days=30),
                "id": uuid.UUID(old["id"]),
            },
        )
        await db.commit()
        member = await _member(staff)
        await db.execute(
            text(
                "INSERT INTO bookings (session_id, member_id, status, created_by) "
                "VALUES (:s, :m, 'booked', "
                "(SELECT id FROM users WHERE email = :e))"
            ),
            {
                "s": uuid.UUID(old["id"]),
                "m": uuid.UUID(member["id"]),
                "e": accounts["staff"],
            },
        )
        await db.commit()
        listed = (await staff.get(f"/api/v1/bookings?session_id={old['id']}")).json()
        await staff.post(
            f"/api/v1/bookings/{listed['items'][0]['id']}/settle",
            json={"attended": False},
        )

        after = (await staff.get("/api/v1/dashboard")).json()["headline"]
        assert after["no_shows_this_week"] == before["no_shows_this_week"]

    async def test_members_waitlisted_ignores_sessions_that_have_passed(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Nothing closes out a waitlist entry when its session passes, so an
        unscoped count would include everyone ever waitlisted and could only ever
        grow — a number that is wrong in a way nobody notices for a month."""
        today = await _studio_today(staff)
        session = await _session_at(
            staff, db, accounts, day=today + dt.timedelta(days=7), capacity=1
        )
        await staff.post(
            "/api/v1/bookings",
            json={
                "session_id": session["id"],
                "member_id": (await _member(staff))["id"],
            },
        )
        await staff.post(
            "/api/v1/bookings",
            json={
                "session_id": session["id"],
                "member_id": (await _member(staff))["id"],
            },
        )
        with_future = (await staff.get("/api/v1/dashboard")).json()["headline"]

        await db.execute(
            text("UPDATE sessions SET starts_at = now() - interval '1 day' WHERE id = :id"),
            {"id": uuid.UUID(session["id"])},
        )
        await db.commit()

        after = (await staff.get("/api/v1/dashboard")).json()["headline"]
        assert after["members_waitlisted"] == with_future["members_waitlisted"] - 1


class TestBreakdowns:
    async def test_bookings_are_broken_down_by_status(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        body = (await staff.get("/api/v1/dashboard")).json()

        statuses = {row["status"] for row in body["by_status"]}
        assert statuses <= {
            "booked",
            "waitlisted",
            "cancelled",
            "attended",
            "no_show",
        }
        assert all(row["count"] > 0 for row in body["by_status"])

    async def test_bookings_are_broken_down_by_class(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        today = await _studio_today(staff)
        studio_class = await _class(staff)
        session = await _session_at(
            staff,
            db,
            accounts,
            day=today + dt.timedelta(days=3),
            class_id=studio_class["id"],
        )
        for _ in range(2):
            await staff.post(
                "/api/v1/bookings",
                json={
                    "session_id": session["id"],
                    "member_id": (await _member(staff))["id"],
                },
            )

        body = (await staff.get("/api/v1/dashboard")).json()

        row = next(r for r in body["by_class"] if r["class_id"] == studio_class["id"])
        assert row["count"] == 2
        assert row["class_title"] == studio_class["title"]

    async def test_the_chart_always_has_eight_weeks(self, staff: AsyncClient) -> None:
        """The weeks are generated, not derived from the data, so a quiet week is a
        zero bar rather than a gap in the chart."""
        body = (await staff.get("/api/v1/dashboard")).json()

        weeks = body["attendance_by_week"]
        assert len(weeks) == 8
        assert [w["week_start"] for w in weeks] == sorted(w["week_start"] for w in weeks)

    async def test_the_weeks_are_consecutive_mondays_ending_this_week(
        self, staff: AsyncClient
    ) -> None:
        body = (await staff.get("/api/v1/dashboard")).json()
        weeks = [dt.date.fromisoformat(w["week_start"]) for w in body["attendance_by_week"]]

        assert all(w.weekday() == 0 for w in weeks)
        assert all((b - a).days == 7 for a, b in itertools.pairwise(weeks))
        today = dt.date.fromisoformat(body["as_of"])
        assert weeks[-1] == today - dt.timedelta(days=today.weekday())


class TestDashboardVisibility:
    async def test_an_instructor_sees_only_their_own_teaching(
        self,
        staff: AsyncClient,
        instructor: AsyncClient,
        db: AsyncSession,
        accounts: dict[str, str],
    ) -> None:
        """Goal 1's rule applies here too: the dashboard is scoped by the same
        filter, so an instructor's numbers describe their own sessions."""
        other = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :e, 'x', 'Other', 'instructor')"
            ),
            {"id": other, "e": f"o-{uuid.uuid4().hex[:8]}@example.com"},
        )
        await db.commit()

        today = await _studio_today(staff)
        studio_class = await _class(staff)
        theirs = await staff.post(
            "/api/v1/sessions",
            json={
                "class_id": studio_class["id"],
                "session_date": (today + dt.timedelta(days=2)).isoformat(),
                "start_time": "10:00:00",
                "primary_instructor_id": str(other),
                "room_id": await _room(staff),
            },
        )
        await staff.post(
            "/api/v1/bookings",
            json={
                "session_id": theirs.json()["id"],
                "member_id": (await _member(staff))["id"],
            },
        )

        seen = (await instructor.get("/api/v1/dashboard")).json()

        assert not any(r["class_id"] == studio_class["id"] for r in seen["by_class"])

    async def test_the_response_states_which_day_and_timezone(self, staff: AsyncClient) -> None:
        """A client should never have to guess which day "today" refers to."""
        body = (await staff.get("/api/v1/dashboard")).json()

        assert body["timezone"] == "Asia/Kolkata"
        assert dt.date.fromisoformat(body["as_of"])


class TestMembershipAlerts:
    async def test_a_membership_expiring_soon_appears(self, staff: AsyncClient) -> None:
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=3)).isoformat())

        feed = (await staff.get("/api/v1/alerts/memberships")).json()

        row = next(i for i in feed["items"] if i["member_id"] == member["id"])
        assert row["days_remaining"] == 3
        assert row["has_expired"] is False

    async def test_an_expired_membership_appears(self, staff: AsyncClient) -> None:
        """Goal 10 says "or has already passed" — the ones that lapsed months ago
        are precisely the case the brief opens with."""
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today - dt.timedelta(days=60)).isoformat())

        feed = (await staff.get("/api/v1/alerts/memberships")).json()

        row = next(i for i in feed["items"] if i["member_id"] == member["id"])
        assert row["has_expired"] is True
        assert row["days_remaining"] == -60

    async def test_a_membership_outside_the_window_does_not_appear(
        self, staff: AsyncClient
    ) -> None:
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=30)).isoformat())

        feed = (await staff.get("/api/v1/alerts/memberships")).json()

        assert all(i["member_id"] != member["id"] for i in feed["items"])

    async def test_the_boundary_day_is_included(self, staff: AsyncClient) -> None:
        """ "Within the next seven days" includes the seventh."""
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=7)).isoformat())

        feed = (await staff.get("/api/v1/alerts/memberships")).json()

        assert any(i["member_id"] == member["id"] for i in feed["items"])

    async def test_expired_members_sort_first(self, staff: AsyncClient) -> None:
        feed = (await staff.get("/api/v1/alerts/memberships")).json()

        expiries = [i["membership_expiry"] for i in feed["items"]]
        assert expiries == sorted(expiries)

    async def test_the_badge_count_matches_the_feed(self, staff: AsyncClient) -> None:
        feed = (await staff.get("/api/v1/alerts/memberships")).json()
        badge = (await staff.get("/api/v1/alerts/memberships/count")).json()

        assert badge["count"] == feed["count"] == len(feed["items"])

    async def test_only_staff_can_see_alerts(self, instructor: AsyncClient) -> None:
        """Goal 10 assigns dismissal to staff, and chasing renewals is front-desk
        work rather than anything an instructor acts on."""
        assert (await instructor.get("/api/v1/alerts/memberships")).status_code == 403
        assert (await instructor.get("/api/v1/alerts/memberships/count")).status_code == 403


class TestDismissAndRetrigger:
    async def test_dismissing_removes_it_from_the_feed(self, staff: AsyncClient) -> None:
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=2)).isoformat())

        response = await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        assert response.status_code == 204
        feed = (await staff.get("/api/v1/alerts/memberships")).json()
        assert all(i["member_id"] != member["id"] for i in feed["items"])

    async def test_the_badge_count_drops_too(self, staff: AsyncClient) -> None:
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=2)).isoformat())
        before = (await staff.get("/api/v1/alerts/memberships/count")).json()["count"]

        await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        after = (await staff.get("/api/v1/alerts/memberships/count")).json()["count"]
        assert after == before - 1

    async def test_the_alert_returns_when_a_new_expiry_enters_the_window(
        self, staff: AsyncClient
    ) -> None:
        """The last sentence of goal 10, and the whole reason the dismissal stores
        an expiry *value* rather than a boolean.

        Dismiss at a near date, extend well beyond the window (gone), then move the
        new date inside the window — and it comes back without anything having been
        reset.
        """
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=2)).isoformat())
        await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        await staff.patch(
            f"/api/v1/members/{member['id']}",
            json={"membership_expiry": (today + dt.timedelta(days=90)).isoformat()},
        )
        far = (await staff.get("/api/v1/alerts/memberships")).json()
        assert all(i["member_id"] != member["id"] for i in far["items"])

        await staff.patch(
            f"/api/v1/members/{member['id']}",
            json={"membership_expiry": (today + dt.timedelta(days=4)).isoformat()},
        )
        near = (await staff.get("/api/v1/alerts/memberships")).json()

        assert any(i["member_id"] == member["id"] for i in near["items"])

    async def test_reverting_to_the_dismissed_date_still_alerts(self, staff: AsyncClient) -> None:
        """The case value-matching alone misses, closed by the database trigger:
        dismiss, extend the expiry, then correct it back to the original date. The
        old dismissal row would match again and suppress an alert for a member who
        genuinely needs one."""
        today = await _studio_today(staff)
        original = (today + dt.timedelta(days=3)).isoformat()
        member = await _member(staff, expiry=original)
        await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        await staff.patch(
            f"/api/v1/members/{member['id']}",
            json={"membership_expiry": (today + dt.timedelta(days=120)).isoformat()},
        )
        await staff.patch(f"/api/v1/members/{member['id']}", json={"membership_expiry": original})

        feed = (await staff.get("/api/v1/alerts/memberships")).json()

        assert any(i["member_id"] == member["id"] for i in feed["items"])

    async def test_dismissing_twice_is_harmless(self, staff: AsyncClient) -> None:
        """Idempotent rather than a 409: a double-clicked dismiss button should not
        produce an error for an operation that has already achieved its purpose."""
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=2)).isoformat())

        first = await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")
        second = await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        assert first.status_code == second.status_code == 204

    async def test_dismissing_a_membership_that_is_not_expiring_is_rejected(
        self, staff: AsyncClient
    ) -> None:
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=365)).isoformat())

        response = await staff.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        assert response.status_code == 422
        assert "not expiring soon" in response.json()["message"]

    async def test_an_instructor_cannot_dismiss(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        today = await _studio_today(staff)
        member = await _member(staff, expiry=(today + dt.timedelta(days=2)).isoformat())

        response = await instructor.post(f"/api/v1/alerts/memberships/{member['id']}/dismiss")

        assert response.status_code == 403
