"""SS-022 -- ``IWeatherProvider`` implementation calling Open-Meteo's free,
no-key forecast API.

``[VERIFIED 2026-08-14]`` against the real endpoint (see
``docs/worklog/SS-022.md``'s Developer entry for the fetched response and
WMO code table): ``GET https://api.open-meteo.com/v1/forecast
?latitude={lat}&longitude={lng}&current=temperature_2m,relative_humidity_2m
,weather_code,precipitation&timezone=Asia%2FKolkata`` returns
``{"current": {"time": "...", "temperature_2m": 28.2,
"relative_humidity_2m": 79, "weather_code": 53, "precipitation": 0.20},
"current_units": {"precipitation": "mm", "weather_code": "wmo code", ...}}``
-- the field is ``weather_code`` (not ``weathercode``), and
``precipitation`` is in **mm**, exactly as this adapter assumes.

``httpx.AsyncClient(timeout=3.0)`` -- deliberately tighter than the 5.0s
every other client in this repo uses (``tag_cache.py``), because unlike
those this call sits on the synchronous critical path of an endpoint with a
stated latency AC. No retry (a retry would double the worst case for a
purely decorative-plus-advisory signal).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from adapters.interfaces import IWeatherProvider, WeatherObservation

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT_SECONDS = 3.0


class OpenMeteoWeatherAdapter(IWeatherProvider):
    """``base_url`` overridable via ``OPEN_METEO_BASE_URL`` env var, for
    tests only -- unset in production, not a secret, not a required key."""

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_current(self, *, lat: float, lng: float) -> WeatherObservation | None:
        base_url = os.getenv("OPEN_METEO_BASE_URL", _DEFAULT_BASE_URL)
        params: dict[str, str | float] = {
            "latitude": lat,
            "longitude": lng,
            "current": "temperature_2m,relative_humidity_2m,weather_code,precipitation",
            "timezone": "Asia/Kolkata",
        }
        try:
            if self._client is not None:
                response = await self._client.get(base_url, params=params, timeout=_TIMEOUT_SECONDS)
            else:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    response = await client.get(base_url, params=params)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            current = body["current"]
            return WeatherObservation(
                temp_c=float(current["temperature_2m"]),
                humidity=int(current["relative_humidity_2m"]),
                weather_code=int(current["weather_code"]),
                precipitation_mm=float(current["precipitation"]),
                observed_at=str(current["time"]),
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "open_meteo_fetch_failed", extra={"error": str(exc), "lat": lat, "lng": lng}
            )
            return None
