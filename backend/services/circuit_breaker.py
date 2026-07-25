"""Redis-backed (Upstash REST, via ``httpx``) circuit breaker protecting
against a Replicate outage (SS-011).

Global (not per-user) state -- the ticket's own AC ("3 consecutive Replicate
calls fail") is naturally read as detecting a systemic Replicate outage, not
one user's problem, so both Redis keys below carry no ``user_id`` component
(Architect's own reasonable choice, not a ticket-pinned name).

**Fails "closed-circuit" (i.e., proceeds with the Replicate call) on
Redis-unavailable** -- the opposite default from ``DailyRateLimiter`` in
``rate_limiter.py``, deliberately: this is a resilience/UX optimization, not
a security or money-gating boundary. A missed circuit-open decision costs at
most a few wasted $0.0023 calls; blocking *all* BG removal because Upstash
briefly hiccuped would be a worse trade. See docs/tickets/SS-011-design.md's
"Concrete values" for the full reasoning.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_FAILURES_KEY = "stylesense:bg_removal_circuit:consecutive_failures"
_OPEN_UNTIL_KEY = "stylesense:bg_removal_circuit:open_until"


class CircuitBreaker:
    """Opens after ``failure_threshold`` consecutive Replicate failures,
    auto-closes after ``open_seconds``."""

    def __init__(self, failure_threshold: int = 3, open_seconds: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds

    async def is_open(self) -> bool:
        """Returns True if the circuit is currently open (skip Replicate
        entirely, go straight to the bg_pending fallback). Fails
        "closed-circuit" (returns False, i.e. proceeds) if Upstash is
        unconfigured or the REST call errors."""
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            logger.warning("circuit_breaker_env_unset")
            return False

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.post(f"{url}/get/{_OPEN_UNTIL_KEY}", headers=headers)
                response.raise_for_status()
                body = response.json()
                if body.get("error"):
                    raise httpx.HTTPError(f"Upstash GET error: {body['error']}")
                open_until_raw = body.get("result")
            except httpx.HTTPError as exc:
                logger.warning("circuit_breaker_get_error", extra={"error": str(exc)})
                return False

        if not open_until_raw:
            return False

        try:
            open_until = float(open_until_raw)
        except (TypeError, ValueError):
            return False

        return time.time() < open_until

    async def record_success(self) -> None:
        """Resets consecutive_failures to 0."""
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            logger.warning("circuit_breaker_env_unset")
            return

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.post(f"{url}/set/{_FAILURES_KEY}/0", headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("circuit_breaker_reset_error", extra={"error": str(exc)})

    async def record_failure(self) -> None:
        """Increments consecutive_failures; if it reaches failure_threshold,
        sets open_until = now + open_seconds."""
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            logger.warning("circuit_breaker_env_unset")
            return

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                incr_response = await client.post(f"{url}/incr/{_FAILURES_KEY}", headers=headers)
                incr_response.raise_for_status()
                incr_body = incr_response.json()
                if incr_body.get("error"):
                    raise httpx.HTTPError(f"Upstash INCR error: {incr_body['error']}")
                consecutive_failures = incr_body.get("result", 0)
            except httpx.HTTPError as exc:
                logger.warning("circuit_breaker_incr_error", extra={"error": str(exc)})
                return

            if consecutive_failures >= self.failure_threshold:
                open_until = time.time() + self.open_seconds
                try:
                    set_response = await client.post(
                        f"{url}/set/{_OPEN_UNTIL_KEY}/{open_until}", headers=headers
                    )
                    set_response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning(
                        "circuit_breaker_set_open_until_error", extra={"error": str(exc)}
                    )
