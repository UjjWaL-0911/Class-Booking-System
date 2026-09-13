"""Health endpoint tests.

These are thin now — the readiness probe gains a real database check when the
engine lands — but the *contract* is fixed here, because Render's health check
and the keep-warm cron both depend on it and neither should have to change later.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_endpoints_sit_outside_the_api_version_prefix(
    client: AsyncClient,
) -> None:
    """Platform probes are infrastructure, not part of the versioned API, so they
    must not move when the API version does."""
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/api/v1/health")).status_code == 404


async def test_unknown_route_is_a_404(client: AsyncClient) -> None:
    assert (await client.get("/does-not-exist")).status_code == 404


class TestHeadProbes:
    """Both health endpoints answer HEAD, not just GET.

    Starlette adds HEAD to any GET route automatically; FastAPI's ``APIRoute``
    overrides that and registers only the methods it is given. So a plain
    ``@router.get`` here answers a HEAD probe with **405** — the path matches, the
    method does not — and an uptime monitor reads that as the service being down
    while it is serving perfectly. Which is exactly what happened the first time
    this was monitored.

    Free uptime checks default to HEAD because it is cheaper, and so do plenty of
    load balancers. These two tests are here because the failure is invisible from
    the application's own side: every human and every browser uses GET.
    """

    async def test_liveness_answers_head(self, api: AsyncClient) -> None:
        response = await api.head("/health")

        assert response.status_code == 200

    async def test_readiness_answers_head(self, api: AsyncClient) -> None:
        response = await api.head("/health/ready")

        assert response.status_code == 200

    async def test_head_carries_no_body(self, api: AsyncClient) -> None:
        """What makes HEAD cheap. Starlette strips it; this asserts it stays so."""
        response = await api.head("/health")

        assert response.content == b""

    async def test_get_is_unchanged(self, api: AsyncClient) -> None:
        """The point of the change was to add a method, not alter one."""
        response = await api.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
