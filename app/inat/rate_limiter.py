"""Async rate limiter for iNaturalist API — adapted from inat_blitz_analysis.py."""

import asyncio
import time


class AsyncRateLimiter:
    """Ensures minimum interval between API requests across all coroutines.

    The iNat API allows ~60 req/min. We default to 1.0s between requests
    which gives us headroom and is polite to the shared resource.
    """

    def __init__(self, min_interval: float = 1.0):
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_time = time.monotonic()
