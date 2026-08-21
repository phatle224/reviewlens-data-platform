"""Small deterministic token-bucket guard for enrichment provider calls."""

from __future__ import annotations

from collections.abc import Callable


class EnrichmentRateLimitExceeded(RuntimeError):
    """Provider dispatch is temporarily denied without a network request."""


class EnrichmentRateLimiter:
    def __init__(
        self,
        *,
        max_requests: int = 2,
        window_seconds: float = 1.0,
        monotonic: Callable[[], float],
    ) -> None:
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("rate limit values must be positive")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._monotonic = monotonic
        self._timestamps: list[float] = []

    def acquire(self) -> None:
        now = self._monotonic()
        self._timestamps = [
            timestamp for timestamp in self._timestamps if now - timestamp < self._window_seconds
        ]
        if len(self._timestamps) >= self._max_requests:
            raise EnrichmentRateLimitExceeded("AI_ENRICHMENT_RATE_LIMITED")
        self._timestamps.append(now)
