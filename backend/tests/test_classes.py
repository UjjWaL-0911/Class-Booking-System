"""Class management tests (goal 2), and the role enforcement from goal 1.

Goal 2's archiving requirement is the substantive part: archiving must hide a class
from default views "without destroying its sessions or bookings". Several tests here
exist specifically to prove nothing was destroyed, because a soft delete that
quietly cascades looks identical from the list endpoint.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")

VALID_CLASS: dict[str, Any] = {
    "title": "Vinyasa Flow",
    "description": "A flowing sequence linking breath to movement.",
    "discipline": "yoga",
    "default_duration_min": 60,
    "default_capacity": 20,
}


def _class_body(**overrides: Any) -> dict[str, Any]:
    """A valid class, with a title nothing else in the suite has used.

    Titles are unique among live classes, and this database is shared and never
    truncated — `booking_events` refuses TRUNCATE by design — so a fixed title
    would pass on a clean database and 409 on every run after it. The tests that
    are *about* the title pass their own.
    """
    return {**VALID_CLASS, "title": f"Vinyasa Flow {uuid.uuid4().hex[:8]}", **overrides}


async def _create(staff: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await staff.post("/api/v1/classes", json=_class_body(**overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestCreate:
    async def test_staff_can_create_a_class(self, staff: AsyncClient) -> None:
        body = await _create(staff)

        assert body["title"].startswith("Vinyasa Flow")
        assert body["discipline"] == "yoga"
        assert body["default_duration_min"] == 60
        assert body["default_capacity"] == 20
        assert body["archived_at"] is None
        # version_id_col starts the counter at 1 on insert, not 0.
        assert body["version"] == 1

    async def test_whitespace_is_trimmed(self, staff: AsyncClient) -> None:
        tag = uuid.uuid4().hex[:8]
        body = await _create(staff, title=f"  Spin Class {tag}  ", discipline=" cycling ")

        assert body["title"] == f"Spin Class {tag}"
        assert body["discipline"] == "cycling"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("title", ""),
            ("discipline", ""),
            ("default_duration_min", 0),
            ("default_duration_min", -30),
            ("default_capacity", 0),
            ("default_capacity", -5),
        ],
    )
    async def test_invalid_values_are_rejected(
        self, staff: AsyncClient, field: str, value: Any
    ) -> None:
        response = await staff.post("/api/v1/classes", json=_class_body(**{field: value}))

        assert response.status_code == 422

    async def test_description_may_be_omitted(self, staff: AsyncClient) -> None:
        payload = {k: v for k, v in _class_body().items() if k != "description"}
        response = await staff.post("/api/v1/classes", json=payload)

        assert response.status_code == 201
        assert response.json()["description"] == ""


class TestRoleEnforcement:
    """Goal 1: the difference "must be enforced on the server, not just hidden in
    the interface". Every one of these calls the API directly with an instructor
    token — what a UI would render is irrelevant."""

    async def test_an_instructor_cannot_create_a_class(self, instructor: AsyncClient) -> None:
        response = await instructor.post("/api/v1/classes", json=_class_body())

        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"

    async def test_an_instructor_cannot_edit_a_class(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        created = await _create(staff)

        response = await instructor.patch(
            f"/api/v1/classes/{created['id']}",
            json={"version": created["version"], "title": "Hijacked"},
        )

        assert response.status_code == 403

    async def test_an_instructor_cannot_archive_or_restore(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        created = await _create(staff)

        assert (
            await instructor.post(f"/api/v1/classes/{created['id']}/archive")
        ).status_code == 403
        assert (
            await instructor.post(f"/api/v1/classes/{created['id']}/restore")
        ).status_code == 403

    async def test_an_instructor_can_read_classes(
        self, staff: AsyncClient, instructor: AsyncClient
    ) -> None:
        """Reading is allowed: an instructor needs the title and discipline of the
        class their session belongs to. Goal 1 bars them from *creating* classes,
        not from knowing what they are teaching."""
        created = await _create(staff)

        listed = await instructor.get("/api/v1/classes")
        fetched = await instructor.get(f"/api/v1/classes/{created['id']}")

        assert listed.status_code == 200
        assert fetched.status_code == 200

    async def test_an_unauthenticated_caller_gets_401(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/classes")).status_code == 401
        assert (await api.post("/api/v1/classes", json=_class_body())).status_code == 401


class TestUpdate:
    async def test_a_partial_update_leaves_other_fields_alone(self, staff: AsyncClient) -> None:
        created = await _create(staff)

        response = await staff.patch(
            f"/api/v1/classes/{created['id']}",
            json={"version": created["version"], "default_capacity": 25},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["default_capacity"] == 25
        assert body["title"] == created["title"]
        assert body["discipline"] == created["discipline"]

    async def test_the_version_increments_on_a_real_change(self, staff: AsyncClient) -> None:
        created = await _create(staff)

        updated = (
            await staff.patch(
                f"/api/v1/classes/{created['id']}",
                json={
                    "version": created["version"],
                    "title": f"Renamed {uuid.uuid4().hex[:8]}",
                },
            )
        ).json()

        assert updated["version"] == created["version"] + 1

    async def test_a_stale_version_is_rejected(self, staff: AsyncClient) -> None:
        """Two staff with the class open, both hitting save. Without this the
        second silently overwrites the first."""
        created = await _create(staff)
        tag = uuid.uuid4().hex[:8]
        stale = created["version"]
        await staff.patch(
            f"/api/v1/classes/{created['id']}",
            json={"version": stale, "title": f"First edit {tag}"},
        )

        second = await staff.patch(
            f"/api/v1/classes/{created['id']}",
            json={"version": stale, "title": f"Second edit {tag}"},
        )

        assert second.status_code == 409
        assert second.json()["code"] == "conflict"
        assert second.json()["details"] == {"expected": stale, "actual": stale + 1}

    async def test_the_first_edit_survives_the_rejected_one(self, staff: AsyncClient) -> None:
        created = await _create(staff)
        tag = uuid.uuid4().hex[:8]
        stale = created["version"]
        await staff.patch(
            f"/api/v1/classes/{created['id']}",
            json={"version": stale, "title": f"First edit {tag}"},
        )
        await staff.patch(
            f"/api/v1/classes/{created['id']}",
            json={"version": stale, "title": f"Second edit {tag}"},
        )

        current = (await staff.get(f"/api/v1/classes/{created['id']}")).json()
        assert current["title"] == f"First edit {tag}"

    async def test_updating_a_missing_class_is_404(self, staff: AsyncClient) -> None:
        response = await staff.patch(
            f"/api/v1/classes/{uuid.uuid4()}", json={"version": 1, "title": "x"}
        )

        assert response.status_code == 404


class TestArchiveAndRestore:
    async def test_archiving_hides_the_class_from_the_default_list(
        self, staff: AsyncClient
    ) -> None:
        created = await _create(staff, title=f"Archive me {uuid.uuid4().hex[:6]}")

        await staff.post(f"/api/v1/classes/{created['id']}/archive")

        titles = [c["title"] for c in (await staff.get("/api/v1/classes")).json()]
        assert created["title"] not in titles

    async def test_archived_classes_are_listed_when_asked_for(self, staff: AsyncClient) -> None:
        created = await _create(staff, title=f"Archive me {uuid.uuid4().hex[:6]}")
        await staff.post(f"/api/v1/classes/{created['id']}/archive")

        response = await staff.get("/api/v1/classes?include_archived=true")

        titles = [c["title"] for c in response.json()]
        assert created["title"] in titles

    async def test_an_archived_class_is_still_reachable_by_id(self, staff: AsyncClient) -> None:
        """Hiding it from lists is the point; making its bookings unreachable is
        not. A direct link must still resolve."""
        created = await _create(staff)
        await staff.post(f"/api/v1/classes/{created['id']}/archive")

        response = await staff.get(f"/api/v1/classes/{created['id']}")

        assert response.status_code == 200
        assert response.json()["archived_at"] is not None

    async def test_restoring_brings_it_back(self, staff: AsyncClient) -> None:
        created = await _create(staff, title=f"Round trip {uuid.uuid4().hex[:6]}")
        await staff.post(f"/api/v1/classes/{created['id']}/archive")

        restored = await staff.post(f"/api/v1/classes/{created['id']}/restore")

        assert restored.status_code == 200
        assert restored.json()["archived_at"] is None
        titles = [c["title"] for c in (await staff.get("/api/v1/classes")).json()]
        assert created["title"] in titles

    async def test_archiving_twice_is_rejected(self, staff: AsyncClient) -> None:
        created = await _create(staff)
        await staff.post(f"/api/v1/classes/{created['id']}/archive")

        second = await staff.post(f"/api/v1/classes/{created['id']}/archive")

        assert second.status_code == 422
        assert "already archived" in second.json()["message"]

    async def test_restoring_a_live_class_is_rejected(self, staff: AsyncClient) -> None:
        created = await _create(staff)

        response = await staff.post(f"/api/v1/classes/{created['id']}/restore")

        assert response.status_code == 422

    async def test_archiving_destroys_nothing(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        """Goal 2 is explicit that archiving must not destroy sessions or bookings.

        From the list endpoint an archived class and a cascade-deleted one look
        identical, so this counts the rows directly.
        """
        created = await _create(staff)
        class_id = uuid.UUID(created["id"])
        tag = uuid.uuid4().hex[:8]

        room_id, user_id, member_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await db.execute(
            text("INSERT INTO rooms (id, name) VALUES (:id, :n)"),
            {"id": room_id, "n": f"Studio {tag}"},
        )
        await db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (:id, :e, 'x', 'Teach', 'instructor')"
            ),
            {"id": user_id, "e": f"teach-{tag}@example.com"},
        )
        await db.execute(
            text(
                "INSERT INTO members (id, full_name, email, membership_expiry) "
                "VALUES (:id, 'Ada', :e, '2027-01-01')"
            ),
            {"id": member_id, "e": f"ada-{tag}@example.com"},
        )
        session_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO sessions (id, class_id, starts_at, "
                "primary_instructor_id, room_id, duration_min, capacity) "
                "VALUES (:id, :c, '2026-11-01 18:00+00', :u, :r, 60, 20)"
            ),
            {"id": session_id, "c": class_id, "u": user_id, "r": room_id},
        )
        await db.execute(
            text(
                "INSERT INTO bookings (session_id, member_id, status, created_by) "
                "VALUES (:s, :m, 'booked', :u)"
            ),
            {"s": session_id, "m": member_id, "u": user_id},
        )
        await db.commit()

        await staff.post(f"/api/v1/classes/{class_id}/archive")

        sessions = (
            await db.execute(
                text("SELECT count(*) FROM sessions WHERE class_id = :c"),
                {"c": class_id},
            )
        ).scalar_one()
        bookings = (
            await db.execute(
                text("SELECT count(*) FROM bookings WHERE session_id = :s"),
                {"s": session_id},
            )
        ).scalar_one()

        assert sessions == 1
        assert bookings == 1


class TestRooms:
    async def test_staff_can_create_and_list_a_room(self, staff: AsyncClient) -> None:
        name = f"Studio {uuid.uuid4().hex[:6]}"

        created = await staff.post("/api/v1/rooms", json={"name": name})
        listed = await staff.get("/api/v1/rooms")

        assert created.status_code == 201
        assert name in [r["name"] for r in listed.json()]

    async def test_a_duplicate_room_name_is_a_readable_409(self, staff: AsyncClient) -> None:
        """The unique constraint would otherwise surface as a 500 with Postgres
        internals in it."""
        name = f"Studio {uuid.uuid4().hex[:6]}"
        await staff.post("/api/v1/rooms", json={"name": name})

        duplicate = await staff.post("/api/v1/rooms", json={"name": name})

        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "conflict"
        assert "already exists" in duplicate.json()["message"]

    async def test_an_instructor_cannot_create_a_room(self, instructor: AsyncClient) -> None:
        response = await instructor.post(
            "/api/v1/rooms", json={"name": f"Studio {uuid.uuid4().hex[:6]}"}
        )

        assert response.status_code == 403


class TestUniqueTitle:
    """One live class per title.

    Two classes called the same thing is a data-entry mistake that costs more
    than it looks: goal 3 schedules a session against a class *by id*, so a
    duplicate silently splits one timetable across two rows, and goal 8's
    breakdown then reports two half-popular classes instead of one busy one.
    """

    async def test_a_duplicate_title_is_refused(self, staff: AsyncClient) -> None:
        body = _class_body(title=f"Unique {uuid.uuid4().hex[:8]}")
        assert (await staff.post("/api/v1/classes", json=body)).status_code == 201

        again = await staff.post("/api/v1/classes", json=body)

        assert again.status_code == 409
        assert "already offered" in again.json()["message"]

    async def test_case_does_not_make_it_a_different_class(
        self, staff: AsyncClient
    ) -> None:
        """"Vinyasa Flow" and "vinyasa flow" are one class to everybody except a
        byte comparison. A case-sensitive rule here would be close to decorative."""
        title = f"Shouted {uuid.uuid4().hex[:8]}"
        made = await staff.post("/api/v1/classes", json=_class_body(title=title))
        assert made.status_code == 201, made.text

        shouted = await staff.post("/api/v1/classes", json=_class_body(title=title.upper()))

        assert shouted.status_code == 409

    async def test_renaming_onto_an_existing_title_is_refused(
        self, staff: AsyncClient
    ) -> None:
        """The insert is the obvious path; the rename is the one a check written
        in the service would have been most likely to miss."""
        taken = _class_body(title=f"Taken {uuid.uuid4().hex[:8]}")
        assert (await staff.post("/api/v1/classes", json=taken)).status_code == 201
        other = (await staff.post("/api/v1/classes", json=_class_body())).json()

        renamed = await staff.patch(
            f"/api/v1/classes/{other['id']}",
            json={"title": taken["title"], "version": other["version"]},
        )

        assert renamed.status_code == 409

    async def test_an_archived_title_can_be_used_again(self, staff: AsyncClient) -> None:
        """Archiving means "not offered any more", and a name nobody is offering
        should be available. The index is partial for exactly this."""
        title = f"Retired {uuid.uuid4().hex[:8]}"
        retiring = (await staff.post("/api/v1/classes", json=_class_body(title=title))).json()
        archived = await staff.post(f"/api/v1/classes/{retiring['id']}/archive")
        assert archived.status_code == 200, archived.text

        reused = await staff.post("/api/v1/classes", json=_class_body(title=title))

        assert reused.status_code == 201

    async def test_restoring_into_a_taken_title_is_refused(
        self, staff: AsyncClient
    ) -> None:
        """Looks like a bug and is not. Restoring would produce exactly the
        duplicate the index exists to prevent, so it has to fail — and it fails
        with a 409 naming the problem rather than a 500."""
        title = f"Contested {uuid.uuid4().hex[:8]}"
        original = (await staff.post("/api/v1/classes", json=_class_body(title=title))).json()
        archived = await staff.post(f"/api/v1/classes/{original['id']}/archive")
        assert archived.status_code == 200, archived.text
        made = await staff.post("/api/v1/classes", json=_class_body(title=title))
        assert made.status_code == 201, made.text

        restored = await staff.post(f"/api/v1/classes/{original['id']}/restore")

        assert restored.status_code == 409

    async def test_the_title_is_trimmed_before_it_is_compared(
        self, staff: AsyncClient
    ) -> None:
        """A trailing space is not a different class. The service strips on the
        way in, so the stored value is what the index compares."""
        title = f"Spaced {uuid.uuid4().hex[:8]}"
        made = await staff.post("/api/v1/classes", json=_class_body(title=title))
        assert made.status_code == 201, made.text

        padded = await staff.post("/api/v1/classes", json=_class_body(title=f"  {title}  "))

        assert padded.status_code == 409
