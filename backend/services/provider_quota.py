"""Per-provider RPM+TPM quota tracker for the styling router (SS-028 §5).

Mechanism, not policy -- modelled on ``services/gemini_rate_limiter.py``'s
sliding window, with three deliberate differences: ``try_reserve()`` is
**non-blocking** (returns ``False`` immediately, NEVER queues -- the raw
ticket's own words: "quota exhausted mid-request-burst -> route new
requests to the alternate provider; do not queue behind an exhausted
pool" -- a blocking acquire here would silently convert a capacity problem
into a latency problem and break ``ai_router_policy``'s deadline); it
tracks BOTH RPM and TPM, not just RPM; ceilings are sourced from
``ai_provider_quota`` config (per provider) rather than a constructor
constant.

**Not a substitute for the per-user rate limit.** ``OutfitSuggestionService``
already runs SS-018's Upstash ``RateLimiter`` before the provider is ever
touched (CLAUDE.md: "rate limit checks via Upstash Redis BEFORE expensive
AI calls"). This tracker is a SECOND, orthogonal gate on VENDOR capacity --
account-wide, keyed by provider only, carrying no ``user_id`` -- exactly
like ``GeminiRateLimiter``'s "global, since RPM is a per-API-key limit, not
a per-user one."

**In-process only.** Same known limitation as ``GeminiRateLimiter``,
``CircuitBreaker``, ``TagCache`` and SS-011's semaphore -- with >1 worker
each process holds a partial view and the real account ceiling can be
exceeded (compounds ``BL-037``). Not claimed as distributed-correct.

A provider absent from the configured ceilings dict is treated as
**UNLIMITED** (no local gate) -- the provider's own 429 then drives
failover via ``ProviderQuotaExhaustedError``. Documented here as a
decision, not an accident (design §4.2).

Clock is injectable (mirrors ``GeminiRateLimiter``) so every window test is
deterministic and none sleep.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable


class ProviderQuotaTracker:
    def __init__(
        self,
        ceilings: dict[str, tuple[int, int]] | None = None,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """``ceilings`` maps provider -> (rpm, tpm). A provider absent from
        this dict is unlimited. A ceiling below 1 is clamped to 1 -- a
        degenerate config value must never produce a permanently-closed
        gate (boundary sweep)."""
        self._ceilings: dict[str, tuple[int, int]] = {
            provider: (max(1, rpm), max(1, tpm))
            for provider, (rpm, tpm) in (ceilings or {}).items()
        }
        self._window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._lock = asyncio.Lock()
        self._request_timestamps: dict[str, deque[float]] = {}
        # (timestamp, token_amount) pairs -- an ESTIMATE at reservation
        # time, reconciled to the real amount by record_usage() (see its
        # own docstring for the reconciliation strategy/limitation).
        self._token_events: dict[str, deque[tuple[float, int]]] = {}

    def set_ceilings(self, ceilings: dict[str, tuple[int, int]]) -> None:
        """Live-applies a freshly-read ``ai_provider_quota`` config value
        onto the SAME shared instance (mirrors
        ``GeminiRateLimiter.set_max_requests``'s precedent) -- this is what
        makes "ceilings read from config, not hardcoded" actually mean "no
        redeploy to change them", not just "read once at process start".
        Existing sliding-window state (in-flight reservations) is
        untouched; only the ceiling comparisons change on the next call.
        Providers no longer present in ``ceilings`` become unlimited;
        providers newly present start gated from this call onward."""
        self._ceilings = {
            provider: (max(1, rpm), max(1, tpm)) for provider, (rpm, tpm) in ceilings.items()
        }

    async def try_reserve(self, provider: str, *, estimated_tokens: int) -> bool:
        """Non-blocking. Reserves one RPM slot + ``estimated_tokens`` of
        TPM budget for ``provider`` if both fit within the ceiling;
        otherwise returns ``False`` immediately -- NEVER queues/blocks. A
        provider with no configured ceiling always succeeds (unlimited)."""
        ceiling = self._ceilings.get(provider)
        if ceiling is None:
            return True
        rpm_ceiling, tpm_ceiling = ceiling

        async with self._lock:
            now = self._clock()
            requests = self._request_timestamps.setdefault(provider, deque())
            tokens = self._token_events.setdefault(provider, deque())
            self._evict(requests, now)
            self._evict_tokens(tokens, now)

            current_tokens = sum(amount for _, amount in tokens)
            if len(requests) >= rpm_ceiling or current_tokens + estimated_tokens > tpm_ceiling:
                return False

            requests.append(now)
            tokens.append((now, estimated_tokens))
            return True

    async def record_usage(self, provider: str, *, tokens_in: int, tokens_out: int) -> None:
        """Reconciles the TPM window with the REAL token count after a call
        returns. ``try_reserve``'s pre-call estimate is deliberately
        conservative (over-estimating is the safe direction, per its own
        docstring) -- this replaces the most recent reservation's estimate
        with the real total, so the next ``try_reserve`` call reflects real
        spend rather than the estimate.

        Known limitation: this assumes calls reconcile in roughly
        reservation order (true for the router's own usage pattern -- one
        in-flight call per attempt, ``record_usage`` called immediately
        after that same attempt's response) -- it is NOT a per-reservation
        ledger keyed by a call ID, and out-of-order reconciliation under
        heavy concurrency could misattribute which reservation an update
        applies to. Same in-process, best-effort class of limitation as the
        rest of this module.
        """
        ceiling = self._ceilings.get(provider)
        if ceiling is None:
            return
        async with self._lock:
            now = self._clock()
            tokens = self._token_events.setdefault(provider, deque())
            self._evict_tokens(tokens, now)
            if tokens:
                tokens.pop()
            tokens.append((now, tokens_in + tokens_out))

    def _evict(self, requests: deque[float], now: float) -> None:
        while requests and now - requests[0] >= self._window_seconds:
            requests.popleft()

    def _evict_tokens(self, tokens: deque[tuple[float, int]], now: float) -> None:
        while tokens and now - tokens[0][0] >= self._window_seconds:
            tokens.popleft()


def estimate_tokens(text_length_chars: int, *, output_allowance: int = 512, min_tokens: int = 32) -> int:
    """Cheap pre-call ESTIMATE (design §5: "prompt characters / 4, floored
    at a documented minimum, plus a configured output allowance"). Labelled
    an estimate deliberately -- ``ProviderQuotaTracker.record_usage``
    reconciles with the real count after the call returns. Over-estimating
    is the safe direction."""
    input_estimate = max(min_tokens, text_length_chars // 4)
    return input_estimate + output_allowance
