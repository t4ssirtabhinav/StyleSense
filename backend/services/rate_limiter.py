"""Thin wrapper around Upstash Redis's REST API for per-user rate limiting.

Placement note (per docs/tickets/SS-006-design.md's "Open questions" #6):
this isn't a business-logic service like ``OutfitSuggestionService``, nor an
AI/DB adapter -- ``services/`` is the closest existing fit CLAUDE.md's
folder structure names. Flagged explicitly rather than silently picked.

Uses ``httpx`` (already a dependency -- no new package added for this stub).

REST command shape: ``POST {url}/incr/{key}`` and
``POST {url}/expire/{key}/{seconds}/NX`` -- ``[VERIFIED 2026-07-23,
upstash.com/docs/redis/features/restapi]``, confirmed directly against
Upstash's published REST API docs (fetched by the orchestrator after the
Architect subagent's own pass lacked web tooling despite the task briefing
assuming otherwise -- see the design doc's "Tooling discrepancy" addendum).
The JSON-body ``"error"`` key check (self-attack finding, see design doc)
remains a defensive measure rather than something the docs explicitly
described, but does not conflict with anything verified.

Race handling (SS-018): ``EXPIRE ... NX`` is now called unconditionally
after every successful ``INCR`` (not gated on ``count == 1``), which makes
it idempotent -- concurrent first-requests each calling it is harmless
(only the first actually applies; NX makes the rest no-ops), and a crash
between the ``INCR`` and ``EXPIRE`` calls self-heals on the *next* request
for the same key (which will still see "no TTL yet" and set it then)
instead of leaking a permanently-TTL-less key. This is not full atomicity
(still two HTTP round-trips) -- accepted as sufficient for a per-user,
60-second rate-limit counter; see docs/tickets/SS-018-design.md's "Race
elimination" section for the full reasoning and the rejected atomic-
pipeline alternative.

Fails **CLOSED** by default (denies the request, logs a warning) when
``UPSTASH_REDIS_REST_URL``/``UPSTASH_REDIS_REST_TOKEN`` are unset, or the
REST call errors -- opt back into the old fail-open behavior only via the
explicit ``fail_open=True`` constructor argument. ``OutfitSuggestionService``
passes this for its `MockStylingAdapter`-only construction path to keep
that zero-cost usage working unchanged (see SS-018 design doc). Never
default a real, costed adapter's call site to ``fail_open=True``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_KEY_PREFIX = "stylesense:outfit_suggestions:rate_limit"
_IST = ZoneInfo("Asia/Kolkata")


class RateLimiter:
    """Per-``user_id`` rate limiter backed by Upstash Redis's REST API.

    Fails **closed** by default on any infra gap (unset env vars, REST
    error, or an error body from Upstash) -- pass ``fail_open=True`` to opt
    into fail-open behavior for a zero-cost/non-production caller (e.g.
    ``MockStylingAdapter`` today). Never opt a real, costed adapter into
    ``fail_open=True``.
    """

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: int = 60,
        *,
        fail_open: bool = False,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.fail_open = fail_open

    async def check_and_increment(self, user_id: str) -> bool:
        """Returns True if the request is allowed, False if rate-limited --
        or, on an infra gap (Upstash unconfigured or the REST call errors),
        returns ``self.fail_open`` (default False -- deny; pass
        ``fail_open=True`` at construction to allow instead).
        """
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not url or not token:
            logger.warning(
                "rate_limiter_env_unset",
                extra={"user_id": user_id, "fail_open": self.fail_open},
            )
            return self.fail_open

        key = f"{_KEY_PREFIX}:{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                incr_response = await client.post(f"{url}/incr/{key}", headers=headers)
                incr_response.raise_for_status()
                incr_body = incr_response.json()
                if incr_body.get("error"):
                    raise httpx.HTTPError(f"Upstash INCR error: {incr_body['error']}")
                count = incr_body.get("result", 0)
            except httpx.HTTPError as exc:
                logger.warning(
                    "rate_limiter_incr_error",
                    extra={"user_id": user_id, "error": str(exc), "fail_open": self.fail_open},
                )
                return self.fail_open

            # Best-effort TTL maintenance -- always attempted, never gated on
            # `count == 1`. NX ("only if the key has no TTL yet") makes this
            # idempotent: harmless if concurrent requests both send it, and
            # self-healing if a prior request crashed before reaching this
            # line. A failure here is logged but does NOT flip the
            # allow/deny decision already computed from `count` above.
            try:
                expire_response = await client.post(
                    f"{url}/expire/{key}/{self.window_seconds}/NX", headers=headers
                )
                expire_response.raise_for_status()
                expire_body = expire_response.json()
                if expire_body.get("error"):
                    raise httpx.HTTPError(f"Upstash EXPIRE error: {expire_body['error']}")
            except httpx.HTTPError as exc:
                logger.warning(
                    "rate_limiter_expire_error",
                    extra={"user_id": user_id, "error": str(exc)},
                )

        return bool(count <= self.max_requests)


def _seconds_until_next_ist_midnight(now: datetime | None = None) -> int:
    """Exact seconds remaining until the next 00:00 IST (Asia/Kolkata), not a
    fixed 86400 -- this, combined with the IST-date-in-key, is what makes
    "resets at IST midnight, not UTC" literally true rather than an
    approximate rolling window."""
    current = now.astimezone(_IST) if now else datetime.now(_IST)
    next_midnight = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((next_midnight - current).total_seconds()))


class DailyRateLimiter:
    """Per-``user_id``-per-IST-calendar-day rate limiter for a real, costed
    Replicate call (SS-011). Kept as a separate class from ``RateLimiter``
    above -- different reset semantics (IST-midnight day boundary vs. a
    fixed rolling window) -- rather than overloading one class with two
    incompatible TTL strategies.

    **Fails closed by default** (denies the request) on Redis-unavailable --
    matching ``RateLimiter``'s SS-018-established convention for a real,
    costed gate. This directly protects real money exposure, unlike
    ``CircuitBreaker`` (see circuit_breaker.py), which deliberately fails the
    opposite way since it's a resilience heuristic, not a money gate.
    """

    def __init__(self, max_requests: int = 20, *, fail_open: bool = False) -> None:
        self.max_requests = max_requests
        self.fail_open = fail_open

    async def check_and_increment(self, user_id: str, *, skip: bool = False) -> bool:
        """``skip=True`` (premium/premium_annual) returns True immediately,
        with zero Redis round-trips at all -- mirrors SS-010's "skip the
        check entirely for premium" convention."""
        if skip:
            return True

        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not url or not token:
            logger.warning(
                "daily_rate_limiter_env_unset",
                extra={"user_id": user_id, "fail_open": self.fail_open},
            )
            return self.fail_open

        ist_date = datetime.now(_IST).strftime("%Y-%m-%d")
        key = f"bg_remove:{user_id}:{ist_date}"
        headers = {"Authorization": f"Bearer {token}"}
        ttl_seconds = _seconds_until_next_ist_midnight()

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                incr_response = await client.post(f"{url}/incr/{key}", headers=headers)
                incr_response.raise_for_status()
                incr_body = incr_response.json()
                if incr_body.get("error"):
                    raise httpx.HTTPError(f"Upstash INCR error: {incr_body['error']}")
                count = incr_body.get("result", 0)
            except httpx.HTTPError as exc:
                logger.warning(
                    "daily_rate_limiter_incr_error",
                    extra={"user_id": user_id, "error": str(exc), "fail_open": self.fail_open},
                )
                return self.fail_open

            # Best-effort TTL maintenance -- always attempted, never gated on
            # `count == 1`. NX makes this idempotent (see RateLimiter above
            # for the same established SS-018 reasoning).
            try:
                expire_response = await client.post(
                    f"{url}/expire/{key}/{ttl_seconds}/NX", headers=headers
                )
                expire_response.raise_for_status()
                expire_body = expire_response.json()
                if expire_body.get("error"):
                    raise httpx.HTTPError(f"Upstash EXPIRE error: {expire_body['error']}")
            except httpx.HTTPError as exc:
                logger.warning(
                    "daily_rate_limiter_expire_error",
                    extra={"user_id": user_id, "error": str(exc)},
                )

        return bool(count <= self.max_requests)
