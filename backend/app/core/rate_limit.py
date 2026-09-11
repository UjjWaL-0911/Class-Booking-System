"""Login rate limiting.

An in-process fixed-window counter. That is the right choice *because* this
deployment runs a single instance, and it stops being the right choice the moment
there are two — at which point the state has to move somewhere shared. It is
listed as a known weakness in architecture.md for exactly that reason, rather than
presented as a general solution.

Two keys per attempt, and both matter:

* **Per email** stops someone working through a password list against one account.
* **Per client address** stops someone working through an account list from one
  machine, which the email key alone would miss entirely.

The address comes from ``X-Forwarded-For``, not from the socket. Behind the static
site's rewrite every request arrives from the same proxy, so keying on the socket
address would put every user in one bucket — useless as a defence and a
self-inflicted outage for everyone trying to sign in.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from app.core.errors import DomainError


class RateLimited(DomainError):
    """Too many attempts in the window.

    429 rather than 401: the caller needs to know that the answer is "later", not
    "wrong". ``Retry-After`` carries how much later.
    """

    status_code = 429
    code = "rate_limited"


@dataclass
class _Window:
    """Timestamps of recent attempts against one key.

    A deque of instants rather than a counter with a reset time, so the window
    slides. A plain fixed window lets an attacker make twice the allowance across
    a boundary — five at 0:59 and five more at 1:01.
    """

    hits: deque[float] = field(default_factory=deque)


class LoginRateLimiter:
    """Sliding-window limiter over a bounded in-memory map."""

    def __init__(self, *, limit: int, window_seconds: int, max_keys: int = 10_000) -> None:
        self._limit = limit
        self._window = float(window_seconds)
        self._max_keys = max_keys
        self._buckets: dict[str, _Window] = {}

    def check(self, *, email: str, client_ip: str | None, now: float | None = None) -> None:
        """Raise ``RateLimited`` if either key is over its allowance.

        Called before the password is verified — checking afterwards would mean an
        attacker still gets one argon2 hash per attempt, which is the expensive
        thing this is protecting.
        """
        moment = now if now is not None else time.monotonic()
        keys = [f"email:{email.strip().lower()}"]
        if client_ip:
            keys.append(f"ip:{client_ip}")

        # Evaluated before anything is recorded, so one key being over the limit
        # does not consume the other key's allowance.
        for key in keys:
            window = self._buckets.get(key)
            if window is None:
                continue
            self._evict_old(window, moment)
            if len(window.hits) >= self._limit:
                retry_after = max(1, int(self._window - (moment - window.hits[0])) + 1)
                raise RateLimited(
                    "Too many sign-in attempts. Please wait and try again.",
                    retry_after_seconds=retry_after,
                )

        for key in keys:
            self._record(key, moment)

    def reset(self, *, email: str, client_ip: str | None) -> None:
        """Clear the counters after a successful sign-in.

        Without this, somebody who mistypes their password four times and then gets
        it right stays one attempt from being locked out for the rest of the window.
        """
        self._buckets.pop(f"email:{email.strip().lower()}", None)
        if client_ip:
            self._buckets.pop(f"ip:{client_ip}", None)

    def _record(self, key: str, moment: float) -> None:
        window = self._buckets.setdefault(key, _Window())
        self._evict_old(window, moment)
        window.hits.append(moment)
        self._prune(moment)

    def _evict_old(self, window: _Window, moment: float) -> None:
        cutoff = moment - self._window
        while window.hits and window.hits[0] <= cutoff:
            window.hits.popleft()

    def _prune(self, moment: float) -> None:
        """Keep the map bounded.

        Unbounded, this is a memory leak with a remote trigger: every distinct email
        anybody tries creates a permanent entry. Pruning only runs when the map is
        oversized, so the common path stays O(1).
        """
        if len(self._buckets) <= self._max_keys:
            return
        cutoff = moment - self._window
        stale = [
            key
            for key, window in self._buckets.items()
            if not window.hits or window.hits[-1] <= cutoff
        ]
        for key in stale:
            del self._buckets[key]
