"""Small in-memory sliding-window rate limiter, applied per client address.

It is deliberately simple: state lives in this process, so with several workers
or instances each one counts separately. A shared store (for example Redis) is
the production replacement; see the README.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request

from app.errors import RateLimitExceededError

WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 10_000


class RateLimiter:
    def __init__(
        self,
        limit_per_minute: int,
        trust_proxy_headers: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit_per_minute
        self._trust_proxy_headers = trust_proxy_headers
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_id(self, request: Request) -> str:
        if self._trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        """Record one request; raise RateLimitExceededError when over the limit."""
        now = self._clock()
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            self._hits.clear()  # crude memory bound; acceptable for a single small instance
        hits = self._hits[self._client_id(request)]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._limit:
            retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
            raise RateLimitExceededError(
                "Too many analysis requests. Please wait a moment and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency for the analysis endpoints."""
    request.app.state.rate_limiter.check(request)
