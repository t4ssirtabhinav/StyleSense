"""Thin wrapper around Upstash Redis's REST API for per-user rate limiting.

Placement note (per docs/tickets/SS-006-design.md's "Open questions" #6):
this isn't a business-logic service like ``OutfitSuggestionService``, nor an
AI/DB adapter -- ``services/`` is the closest existing fit CLAUDE.md's
folder structure names. Flagged explicitly rather than silently picked.

Uses ``httpx`` (already a dependency -- no new package added for this stub).
The exact Upstash REST command shape (``POST {url}/incr/{key}`` /
``POST {url}/expire/{key}/{seconds}``) is trained-knowledge, not verified
against Upstash's current docs this pass (no web-fetch tool available) --
see BL-035. Must be verified before this is load-bearing for a real, costed
AI adapter.

Fails OPEN (allows the request, logs a warning) when
``UPSTASH_REDIS_REST_URL``/``UPSTASH_REDIS_REST_TOKEN`` are unset, which is
true today (``.env.example``). This is only acceptable while the guarded
resource is a zero-cost mock adapter -- must flip to fail-closed before a
real, costed adapter replaces it (see design doc's Open Questions #3).
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_KEY_PREFIX = "stylesense:outfit_suggestions:rate_limit"


class RateLimiter:
    """Per-``user_id`` rate limiter backed by Upstash Redis's REST API."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check_and_increment(self, user_id: str) -> bool:
        """Returns True if the request is allowed, False if rate-limited.

        Fails open (returns True, logs a warning) if Upstash env vars are
        unset, or if the Upstash REST call itself errors out -- a rate
        limiter outage must never itself block requests to a zero-cost mock.
        """
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not url or not token:
            logger.warning(
                "rate_limiter_fail_open",
                extra={"user_id": user_id, "reason": "upstash_env_vars_unset"},
            )
            return True

        key = f"{_KEY_PREFIX}:{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                incr_response = await client.post(f"{url}/incr/{key}", headers=headers)
                incr_response.raise_for_status()
                count = incr_response.json().get("result", 0)

                if count == 1:
                    # First request in this window -- set the TTL so the
                    # counter resets after `window_seconds`.
                    await client.post(
                        f"{url}/expire/{key}/{self.window_seconds}", headers=headers
                    )

                return bool(count <= self.max_requests)
        except httpx.HTTPError as exc:
            logger.warning(
                "rate_limiter_error_fail_open",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return True
