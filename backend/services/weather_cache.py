"""SS-022 -- Upstash JSON-blob cache for per-city-per-hour weather
observations, a near-verbatim structural copy of
``services/tag_cache.py`` (same ``_command()`` POST-command-in-body helper,
same fail-open posture -- ``[VERIFIED 2026-07-25,
upstash.com/docs/redis/features/restapi.md]``, re-used not re-verified).

Key scheme: ``weather:v1:{city_slug}:{ist_hour}`` where ``ist_hour =
datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%dT%H")`` -- the same
inline-IST idiom ``services/rate_limiter.py``'s ``DailyRateLimiter`` already
uses. ``SET ... EX 3600`` belt-and-braces: the key rolls at the hour
boundary AND expires. This is the ticket's "cached per city per hour."

Fails open in both directions: unset env / HTTP error / bad JSON -> ``get``
returns ``None`` (fetch fresh), ``set`` is a silent no-op. Never raises.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600
_IST = ZoneInfo("Asia/Kolkata")


def _ist_hour() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H")


def _weather_key(city_slug: str, *, ist_hour: str | None = None) -> str:
    hour = ist_hour if ist_hour is not None else _ist_hour()
    return f"weather:v1:{city_slug}:{hour}"


class WeatherCache:
    async def get(self, city_slug: str) -> dict[str, Any] | None:
        result = await self._command(["GET", _weather_key(city_slug)])
        if not isinstance(result, str):
            return None
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            logger.warning("weather_cache_corrupt_entry", extra={"city_slug": city_slug})
            return None
        return parsed if isinstance(parsed, dict) else None

    async def set(self, city_slug: str, payload: dict[str, Any]) -> None:
        await self._command(
            ["SET", _weather_key(city_slug), json.dumps(payload), "EX", str(_TTL_SECONDS)]
        )

    async def _command(self, command: list[Any]) -> Any:
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            logger.warning("weather_cache_env_unset", extra={"command": command[0]})
            return None

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=command, headers=headers)
                response.raise_for_status()
                body = response.json()
                if body.get("error"):
                    raise httpx.HTTPError(f"Upstash error: {body['error']}")
                return body.get("result")
        except httpx.HTTPError as exc:
            logger.warning(
                "weather_cache_command_failed", extra={"command": command[0], "error": str(exc)}
            )
            return None
