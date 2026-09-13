"""The public schedule endpoint.

Not one of the ten goals, and the only endpoint in the system an anonymous caller
can reach beyond health and sign-in. So most of these tests are about what it does
*not* return: every field on this response is visible to the internet, and the way
that goes wrong is somebody widening the shape later rather than the shape being
wrong today.
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

PATH = "/api/v1/public/schedule"
SOON = dt.date.today() + dt.timedelta(days=3)


async def _user_id(db: AsyncSession, email: str) -> str:
    row = await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    return str(row.scalar_one())


async def _class(staff: AsyncClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "title": f"Public {uuid.uuid4().hex[:8]}",
        "description": "A flowing sequence linking breath to movement.",
        "discipline": "yoga",
        "default_duration_min": 60,
        "default_capacity": 12,
        **overrides,
    }
    response = await staff.post("/api/v1/classes", json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _session(
    staff: AsyncClient,
    db: AsyncSession,
    accounts: dict[str, str],
    *,
    class_id: str | None = None,
    on: dt.date | None = None,
    at: str = "18:00:00",
    capacity: int = 12,
) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    room = await staff.post("/api/v1/rooms", json={"name": f"Room {tag}"})
    response = await staff.post(
        "/api/v1/sessions",
        json={
            "class_id": class_id or (await _class(staff))["id"],
            "session_date": (on or SOON).isoformat(),
            "start_time": at,
            "primary_instructor_id": await _user_id(db, accounts["instructor"]),
            "room_id": room.json()["id"],
            "capacity": capacity,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _titles(api: AsyncClient, **params: Any) -> set[str]:
    response = await api.get(PATH, params=params)
    assert response.status_code == 200, response.text
    return {s["class_title"] for s in response.json()["sessions"]}


class TestItIsActuallyPublic:
    async def test_no_credentials_are_needed(self, api: AsyncClient) -> None:
        assert (await api.get(PATH)).status_code == 200

    async def test_an_upcoming_class_appears(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)

        assert session["class_title"] in await _titles(api)


class TestWhatItRefusesToSay:
    """Each of these is a field that would be a leak, not a bug."""

    async def test_the_shape_is_exactly_the_public_one(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        await _session(staff, db, accounts)

        row = (await api.get(PATH)).json()["sessions"][0]

        assert set(row) == {
            "session_date",
            "start_time",
            "duration_min",
            "class_title",
            "discipline",
            "description",
            "instructor_name",
            "room_name",
            "spots_remaining",
            "is_full",
        }

    async def test_no_identifiers_leak(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Not one id in the response. An anonymous caller cannot use them anyway,
        and a uuid in a public payload is an invitation to try."""
        await _session(staff, db, accounts)

        body = (await api.get(PATH)).text

        assert "_id" not in body
        assert '"id"' not in body
        assert "version" not in body

    async def test_no_email_addresses_leak(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        await _session(staff, db, accounts)

        assert accounts["instructor"] not in (await api.get(PATH)).text

    async def test_no_member_or_booking_data_leaks(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """A booked class must not tell the internet who booked it."""
        session = await _session(staff, db, accounts, capacity=4)
        member = await staff.post(
            "/api/v1/members",
            json={
                "full_name": "Verity Publica",
                "email": f"verity-{uuid.uuid4().hex[:8]}@example.com",
                "membership_expiry": "2030-01-01",
                "notes": "",
            },
        )
        await staff.post(
            "/api/v1/bookings",
            json={"session_id": session["id"], "member_id": member.json()["id"]},
        )

        body = (await api.get(PATH)).text

        assert "Verity Publica" not in body
        assert "booked_count" not in body
        assert "waitlisted" not in body


class TestTheWindow:
    async def test_a_past_class_is_not_listed(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        old = await _session(
            staff, db, accounts, on=dt.date.today() - dt.timedelta(days=2)
        )

        assert old["class_title"] not in await _titles(api, days=31)

    async def test_a_class_beyond_the_window_is_not_listed(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        far = await _session(staff, db, accounts, on=dt.date.today() + dt.timedelta(days=20))

        assert far["class_title"] not in await _titles(api, days=7)

    async def test_hitting_the_cap_is_reported_rather_than_hidden(
        self, api: AsyncClient
    ) -> None:
        """The shared test database holds far more than the cap, which is what made
        this visible: without the flag the response would keep stating a window it
        had quietly stopped filling."""
        body = (await api.get(PATH, params={"days": 31})).json()

        assert len(body["sessions"]) <= 200
        if len(body["sessions"]) == 200:
            assert body["truncated"] is True
        else:
            assert body["truncated"] is False

    async def test_a_small_window_is_not_truncated(self, api: AsyncClient) -> None:
        body = (await api.get(PATH, params={"days": 1})).json()

        assert body["truncated"] is False

    async def test_the_window_cannot_be_widened_without_limit(self, api: AsyncClient) -> None:
        """No credentials and no ceiling is how one request becomes a whole table."""
        assert (await api.get(PATH, params={"days": 3650})).status_code == 422
        assert (await api.get(PATH, params={"days": 0})).status_code == 422

    async def test_the_response_states_the_window_it_used(self, api: AsyncClient) -> None:
        body = (await api.get(PATH, params={"days": 9})).json()

        assert body["days_ahead"] == 9
        assert dt.date.fromisoformat(body["ends"]) - dt.date.fromisoformat(body["starts"]) == (
            dt.timedelta(days=9)
        )


class TestWhatIsHidden:
    async def test_an_archived_class_is_not_advertised(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Archived means "not offered", and this is the one place that word is
        read by somebody deciding whether to turn up."""
        studio_class = await _class(staff)
        session = await _session(staff, db, accounts, class_id=studio_class["id"])
        assert session["class_title"] in await _titles(api)

        await staff.post(f"/api/v1/classes/{studio_class['id']}/archive")

        assert session["class_title"] not in await _titles(api)

    async def test_a_deleted_session_is_not_advertised(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts)
        await staff.delete(f"/api/v1/sessions/{session['id']}")

        assert session["class_title"] not in await _titles(api)


class TestRemainingSpots:
    async def test_it_counts_down_as_people_book(
        self, api: AsyncClient, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        session = await _session(staff, db, accounts, capacity=2)
        title = session["class_title"]

        def row(body: dict[str, Any]) -> dict[str, Any]:
            return next(s for s in body["sessions"] if s["class_title"] == title)

        first = row((await api.get(PATH)).json())
        assert first["spots_remaining"] == 2
        assert first["is_full"] is False

        for i in range(2):
            member = await staff.post(
                "/api/v1/members",
                json={
                    "full_name": f"Booker {i}",
                    "email": f"b{i}-{uuid.uuid4().hex[:8]}@example.com",
                    "membership_expiry": "2030-01-01",
                    "notes": "",
                },
            )
            await staff.post(
                "/api/v1/bookings",
                json={"session_id": session["id"], "member_id": member.json()["id"]},
            )

        after = row((await api.get(PATH)).json())
        assert after["spots_remaining"] == 0
        assert after["is_full"] is True
