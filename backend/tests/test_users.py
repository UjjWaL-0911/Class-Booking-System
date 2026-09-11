"""The people-who-can-teach list.

Small endpoint, three things worth proving: it is staff only (goal 1's rule is
enforced on the server, not hidden in the interface), it includes staff accounts
as well as instructors — because that is the rule the session service applies when
it validates an instructor id — and it leaves out deactivated accounts, so a
picker can never offer somebody the server would then refuse.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("migrated_schema")


class TestListUsers:
    async def test_staff_see_both_roles(self, staff: AsyncClient, accounts: dict[str, str]) -> None:
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200, response.text
        by_email = {row["email"]: row for row in response.json()}
        # Both appear: any active user may lead a session, so a picker that showed
        # only role='instructor' would disagree with what the server accepts.
        assert accounts["staff"] in by_email
        assert accounts["instructor"] in by_email
        assert by_email[accounts["staff"]]["role"] == "staff"
        assert by_email[accounts["instructor"]]["role"] == "instructor"

    async def test_no_password_hash_is_returned(self, staff: AsyncClient) -> None:
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        for row in response.json():
            assert set(row) == {"id", "email", "full_name", "role"}

    async def test_deactivated_accounts_are_left_out(
        self, staff: AsyncClient, db: AsyncSession, accounts: dict[str, str]
    ) -> None:
        await db.execute(
            text("UPDATE users SET is_active = false WHERE email = :e"),
            {"e": accounts["instructor"]},
        )
        await db.commit()

        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        emails = [row["email"] for row in response.json()]
        assert accounts["instructor"] not in emails

    async def test_sorted_by_name(self, staff: AsyncClient) -> None:
        response = await staff.get("/api/v1/users")

        assert response.status_code == 200
        names = [row["full_name"] for row in response.json()]
        assert names == sorted(names)

    async def test_instructors_are_refused(self, instructor: AsyncClient) -> None:
        response = await instructor.get("/api/v1/users")

        assert response.status_code == 403, response.text

    async def test_signing_in_is_required(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/users")

        assert response.status_code == 401, response.text
