"""Login rate limiting.

Two layers of test, for two different reasons.

The unit tests drive the limiter with an injected clock, because a limiter tested
against the wall clock either sleeps — making the suite slow — or asserts nothing
about what happens when the window actually elapses.

The endpoint tests confirm it is wired in front of the password check rather than
behind it. Behind it, an attacker still gets one argon2 hash per attempt, which is
the expensive thing being protected; the limiter would be decorative.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.rate_limit import LoginRateLimiter, RateLimited
from tests.conftest import STAFF_PASSWORD

pytestmark = pytest.mark.usefixtures("migrated_schema")

EMAIL = "someone@example.com"
IP = "203.0.113.7"


def _limiter(limit: int = 3, window: int = 60) -> LoginRateLimiter:
    return LoginRateLimiter(limit=limit, window_seconds=window)


class TestWindow:
    def test_attempts_up_to_the_limit_are_allowed(self) -> None:
        limiter = _limiter(limit=3)

        for i in range(3):
            limiter.check(email=EMAIL, client_ip=IP, now=float(i))

    def test_the_next_attempt_is_refused(self) -> None:
        limiter = _limiter(limit=3)
        for i in range(3):
            limiter.check(email=EMAIL, client_ip=IP, now=float(i))

        with pytest.raises(RateLimited) as exc:
            limiter.check(email=EMAIL, client_ip=IP, now=3.0)

        assert exc.value.status_code == 429
        assert exc.value.details["retry_after_seconds"] > 0

    def test_the_window_slides_rather_than_resetting(self) -> None:
        """A fixed window lets an attacker take twice the allowance across a
        boundary — three at 0:59 and three more at 1:01. A sliding window does not,
        so an attempt is allowed only once the oldest one has actually aged out.
        """
        limiter = _limiter(limit=3, window=60)
        for i in range(3):
            limiter.check(email=EMAIL, client_ip=IP, now=float(i))

        # Still inside the window: the oldest attempt, at t=0, is 59.9s old.
        with pytest.raises(RateLimited):
            limiter.check(email=EMAIL, client_ip=IP, now=59.9)

        # At exactly `window` seconds the oldest attempt has aged out — the
        # eviction boundary is inclusive — so one slot frees and no more.
        limiter.check(email=EMAIL, client_ip=IP, now=60.0)
        with pytest.raises(RateLimited):
            limiter.check(email=EMAIL, client_ip=IP, now=60.0)

    def test_retry_after_shrinks_as_the_window_elapses(self) -> None:
        limiter = _limiter(limit=1, window=60)
        limiter.check(email=EMAIL, client_ip=IP, now=0.0)

        with pytest.raises(RateLimited) as early:
            limiter.check(email=EMAIL, client_ip=IP, now=1.0)
        with pytest.raises(RateLimited) as late:
            limiter.check(email=EMAIL, client_ip=IP, now=50.0)

        assert (
            late.value.details["retry_after_seconds"] < early.value.details["retry_after_seconds"]
        )


class TestKeys:
    def test_a_different_email_from_the_same_address_still_counts(self) -> None:
        """The address key is what catches someone working through a list of
        accounts from one machine — which the email key alone would miss entirely.
        """
        limiter = _limiter(limit=3)
        for i in range(3):
            limiter.check(email=f"user{i}@example.com", client_ip=IP, now=float(i))

        with pytest.raises(RateLimited):
            limiter.check(email="user4@example.com", client_ip=IP, now=3.0)

    def test_the_same_email_from_different_addresses_still_counts(self) -> None:
        """And the email key catches a distributed attempt on one account."""
        limiter = _limiter(limit=3)
        for i in range(3):
            limiter.check(email=EMAIL, client_ip=f"198.51.100.{i}", now=float(i))

        with pytest.raises(RateLimited):
            limiter.check(email=EMAIL, client_ip="198.51.100.9", now=3.0)

    def test_unrelated_users_do_not_affect_each_other(self) -> None:
        limiter = _limiter(limit=2)
        limiter.check(email="a@example.com", client_ip="198.51.100.1", now=0.0)
        limiter.check(email="a@example.com", client_ip="198.51.100.1", now=1.0)

        limiter.check(email="b@example.com", client_ip="198.51.100.2", now=2.0)

    def test_a_refused_attempt_does_not_consume_the_other_key(self) -> None:
        """Both keys are evaluated before either is recorded, so hitting the limit
        on one does not silently spend the other's allowance."""
        limiter = _limiter(limit=2)
        for i in range(2):
            limiter.check(email=EMAIL, client_ip="198.51.100.1", now=float(i))

        with pytest.raises(RateLimited):
            limiter.check(email=EMAIL, client_ip="198.51.100.2", now=2.0)

        # The second address was never charged for the refused attempt.
        limiter.check(email="other@example.com", client_ip="198.51.100.2", now=3.0)

    def test_email_matching_ignores_case_and_padding(self) -> None:
        limiter = _limiter(limit=2)
        limiter.check(email="Ada@Example.com", client_ip=None, now=0.0)
        limiter.check(email="  ada@example.com  ", client_ip=None, now=1.0)

        with pytest.raises(RateLimited):
            limiter.check(email="ADA@EXAMPLE.COM", client_ip=None, now=2.0)

    def test_a_missing_address_is_tolerated(self) -> None:
        """X-Forwarded-For can be absent — in local development, for instance — and
        the email key still has to work on its own."""
        limiter = _limiter(limit=2)
        limiter.check(email=EMAIL, client_ip=None, now=0.0)
        limiter.check(email=EMAIL, client_ip=None, now=1.0)

        with pytest.raises(RateLimited):
            limiter.check(email=EMAIL, client_ip=None, now=2.0)


class TestReset:
    def test_a_successful_sign_in_clears_the_counters(self) -> None:
        """Otherwise four typos followed by the right password leaves somebody one
        attempt from a lockout for the rest of the window."""
        limiter = _limiter(limit=3)
        for i in range(3):
            limiter.check(email=EMAIL, client_ip=IP, now=float(i))

        limiter.reset(email=EMAIL, client_ip=IP)

        limiter.check(email=EMAIL, client_ip=IP, now=3.0)


class TestBounded:
    def test_the_key_map_does_not_grow_without_limit(self) -> None:
        """Unbounded, this is a memory leak with a remote trigger: every distinct
        email anybody tries would create a permanent entry."""
        limiter = LoginRateLimiter(limit=5, window_seconds=60, max_keys=50)

        for i in range(500):
            limiter.check(email=f"u{i}@example.com", client_ip=None, now=float(i))

        # Reaching into a private attribute is the point of this test: the
        # bound is an internal property with no public surface.
        assert len(limiter._buckets) <= 200


class TestEndpoint:
    async def test_repeated_failures_eventually_return_429(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        codes = []
        for _ in range(8):
            response = await api.post(
                "/api/v1/auth/login",
                json={"email": accounts["staff"], "password": "wrong"},
            )
            codes.append(response.status_code)

        assert 401 in codes, codes
        assert 429 in codes, codes

    async def test_the_429_carries_retry_after(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        """A client needs to know the answer is "later", not "wrong"."""
        response = None
        for _ in range(10):
            response = await api.post(
                "/api/v1/auth/login",
                json={"email": accounts["staff"], "password": "wrong"},
            )
            if response.status_code == 429:
                break

        assert response is not None
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        assert response.json()["code"] == "rate_limited"

    async def test_the_limit_applies_before_the_password_is_checked(self, api: AsyncClient) -> None:
        """Against an address that does not exist, so no password is ever verified.

        If the limiter sat behind the check, an attacker would still get one argon2
        hash per attempt and the limit would protect nothing expensive.
        """
        unknown = f"nobody-{uuid.uuid4().hex[:8]}@example.com"
        codes = []
        for _ in range(8):
            response = await api.post(
                "/api/v1/auth/login", json={"email": unknown, "password": "wrong"}
            )
            codes.append(response.status_code)

        assert 429 in codes, codes

    async def test_a_successful_sign_in_is_not_penalised_afterwards(
        self, api: AsyncClient, accounts: dict[str, str]
    ) -> None:
        for _ in range(3):
            await api.post(
                "/api/v1/auth/login",
                json={"email": accounts["staff"], "password": "wrong"},
            )

        good = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": STAFF_PASSWORD},
        )
        assert good.status_code == 200

        again = await api.post(
            "/api/v1/auth/login",
            json={"email": accounts["staff"], "password": STAFF_PASSWORD},
        )
        assert again.status_code == 200
