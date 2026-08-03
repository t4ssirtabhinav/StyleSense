"""``UpstashRateLimiter(IRateLimiter)`` -- SS-018's verified Upstash REST
fail-open/fail-closed shape, generalised from ``INCR``-by-1 to
``INCRBY``/``DECRBY``-by-amount (SS-029 design §3.7).

REST command shapes used:

    POST {url}/incrby/{key}/{amount}     # amount > 0
    POST {url}/decrby/{key}/{amount}     # refund / negative reconcile -- amount > 0
    POST {url}/expire/{key}/{seconds}/NX # unchanged, SS-018 [VERIFIED 2026-07-23]

``[VERIFIED 2026-07-23, upstash.com/docs/redis/features/restapi]`` covers
only ``/incr/`` and ``/expire/.../NX`` (``services/rate_limiter.py``'s own
docstring). The ``/incrby/``/``/decrby/`` path shapes used here were
**``[VERIFIED 2026-07-30]`` directly against the live Upstash REST API**
during this ticket's Developer phase (this session has no web-fetch tool,
the same gap the Architect pass flagged for itself, so verification was
done behaviorally instead of by reading docs): ran
``UpstashRateLimiter().check_and_consume(key=..., amount=5, ...)`` against
the real, configured Upstash instance and observed
``RateLimitDecision(allowed=True, current=5, ...)`` (i.e. ``/incrby/k/5``
really incremented and returned the new total), then ``adjust(key=...,
delta=-5)`` followed by a zero-amount peek observed ``current=0`` (i.e.
``/decrby/k/5`` really decremented back). Recorded in
``docs/worklog/SS-029.md``. ``BL-001``/``BL-039`` are the precedent for
what happens when this step is skipped -- not skipped here.

``DECRBY`` is used for every negative delta deliberately -- never ``INCRBY``
with a negative number, which would put a leading ``-`` in a URL path
segment.

Error handling copies SS-018's ``rate_limiter.py`` verbatim:
``raise_for_status()``, plus the defensive JSON-body ``"error"`` key check.
"""

from __future__ import annotations

import logging
import os

import httpx

from adapters.interfaces import IRateLimiter, RateLimitDecision

logger = logging.getLogger(__name__)


class UpstashRateLimiter(IRateLimiter):
    """Generic, amount-aware counter over Upstash Redis's REST API.
    ``check_and_consume`` derives its allow/deny decision SOLELY from the
    single atomic ``INCRBY`` round-trip's returned total -- there is no
    ``GET`` anywhere in this class. This is the structural property that
    closes the parallel-burst race (design §4.2)."""

    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not url or not token:
            logger.warning(
                "upstash_rate_limiter_env_unset",
                extra={"key": key, "amount": amount, "fail_open": fail_open},
            )
            return RateLimitDecision(allowed=fail_open, current=None, ceiling=ceiling, degraded=True)

        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                incrby_response = await client.post(
                    f"{url}/incrby/{key}/{amount}", headers=headers
                )
                incrby_response.raise_for_status()
                incrby_body = incrby_response.json()
                if incrby_body.get("error"):
                    raise httpx.HTTPError(f"Upstash INCRBY error: {incrby_body['error']}")
                current = int(incrby_body.get("result", 0))
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                logger.warning(
                    "upstash_rate_limiter_incrby_error",
                    extra={"key": key, "amount": amount, "error": str(exc), "fail_open": fail_open},
                )
                return RateLimitDecision(
                    allowed=fail_open, current=None, ceiling=ceiling, degraded=True
                )

            # Best-effort TTL maintenance -- always attempted, unconditional
            # on `count == 1` (SS-018's idempotent NX pattern). A failure
            # here is logged but never flips the allow/deny decision already
            # computed from `current` above.
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
                    "upstash_rate_limiter_expire_error", extra={"key": key, "error": str(exc)}
                )

        allowed = current <= ceiling
        if not allowed:
            # Refund the increment this call just made -- a rejected call
            # must not permanently inflate the counter (design §4.2).
            await self.adjust(key=key, delta=-amount)

        return RateLimitDecision(allowed=allowed, current=current, ceiling=ceiling, degraded=False)

    async def adjust(self, *, key: str, delta: int) -> None:
        """Never raises. Positive delta -> INCRBY; negative -> DECRBY on
        ``abs(delta)`` (never a negative amount in an INCRBY URL path)."""
        if delta == 0:
            return

        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            logger.warning("upstash_rate_limiter_adjust_env_unset", extra={"key": key})
            return

        command = "decrby" if delta < 0 else "incrby"
        amount = abs(delta)
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.post(f"{url}/{command}/{key}/{amount}", headers=headers)
                response.raise_for_status()
                body = response.json()
                if body.get("error"):
                    raise httpx.HTTPError(f"Upstash {command.upper()} error: {body['error']}")
            except httpx.HTTPError as exc:
                logger.warning(
                    "upstash_rate_limiter_adjust_error",
                    extra={"key": key, "delta": delta, "error": str(exc)},
                )
