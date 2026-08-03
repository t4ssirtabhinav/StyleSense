"""In-process async gate honouring Gemini's tagging-path RPM ceiling
(SS-012; ceiling now config-consumed, SS-028, closing ``BL-076``).

A sliding-window token gate: ``acquire()`` **blocks (queues)** until a slot
frees within the window, rather than rejecting -- satisfies the AC's
"excess queued, not dropped". Global (per-process, not per-user), since RPM
is a per-API-key limit, not a per-user one.

**Known limitation (flagged, same class as SS-011's semaphore and
``CircuitBreaker``/``TagCache``):** in-process state only -- correct for
today's single-``uvicorn``-process reality, needs a distributed (Redis)
rework if this backend is ever deployed with >1 worker (compounds
``BL-037``).

**Ceiling source (SS-028):** the constructor default (``15``) is still the
account's original free-tier figure and is what a missing/malformed
``gemini_quota_ceiling_rpm`` config row falls back to (SS-026's guarantee)
-- ``routers/wardrobe.py::get_gemini_rate_limiter()`` now applies the
LIVE config value onto the shared singleton via ``set_max_requests()``
every request, so raising the ceiling (once the real paid-tier RPM is
read off the dashboard, ``BL-098``) is a config ``UPDATE``, not a code
change. The account's real paid-tier ceiling has not been independently
re-verified as part of this ticket -- do not read the ``15`` default as a
current, verified limit; it is a conservative floor.

This limiter is ALSO one of two independent in-process gates spending the
same Gemini account-wide quota pool -- ``services/provider_quota.py``'s
``ProviderQuotaTracker`` gates the styling path against the same account
(``BL-099``); their ceilings must be apportioned by hand, not summed
automatically.
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

    @property
    def max_requests(self) -> int:
        return self._max_requests

    def set_max_requests(self, max_requests: int) -> None:
        """Live-applies a freshly-read ``gemini_quota_ceiling_rpm`` config
        value onto this SAME shared instance (SS-028, closes ``BL-076``).
        Clamped to >= 1 -- a degenerate config value (0 or negative) must
        never produce a permanently-closed gate. Existing queued/reserved
        timestamps are untouched; only the ceiling comparison in the next
        ``acquire()`` changes."""
        self._max_requests = max(1, max_requests)

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
