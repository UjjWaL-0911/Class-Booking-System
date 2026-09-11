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
