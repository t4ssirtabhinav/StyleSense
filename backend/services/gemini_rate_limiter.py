"""In-process async gate honouring Gemini's 15 RPM free-tier limit (SS-012).

A sliding-window token gate: ``acquire()`` **blocks (queues)** until a slot
frees within the window, rather than rejecting -- satisfies the AC's
"excess queued, not dropped". Global (per-process, not per-user), since 15
RPM is a per-API-key limit, not a per-user one.

**Known limitation (flagged, same class as SS-011's semaphore and
``CircuitBreaker``/``TagCache``):** in-process state only -- correct for
today's single-``uvicorn``-process reality, needs a distributed (Redis)
rework if this backend is ever deployed with >1 worker (compounds
``BL-037``).

Note: the user's own Gemini dashboard confirms the account's real limits
are 15 RPM / 500K TPM / 500 RPD on the free tier -- 500 RPD is a second
bound this in-process limiter does not enforce (the per-user cost cap gap
is tracked separately as ``BL-062``).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable


class GeminiRateLimiter:
    def __init__(
        self,
        max_requests: int = 15,
        window_seconds: float = 60.0,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._lock = asyncio.Lock()
        self._timestamps: deque[float] = deque()

    async def acquire(self) -> None:
        """Blocks until a slot is free within the sliding window, then
        reserves it. Never rejects -- an over-budget caller queues instead
        of erroring, per the AC."""
        while True:
            async with self._lock:
                now = self._clock()
                self._evict_expired(now)
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                wait_seconds = self._window_seconds - (now - self._timestamps[0])

            # Sleep outside the lock so other callers can also check/evict
            # while this one waits -- avoids one waiter serializing everyone
            # else behind it for the full wait duration.
            await asyncio.sleep(max(wait_seconds, 0.01))

    def _evict_expired(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= self._window_seconds:
            self._timestamps.popleft()
