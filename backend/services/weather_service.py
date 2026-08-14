"""SS-022 -- ``WeatherService``: the orchestrator, and the only thing the
portfolio service knows about (design §2). City read -> cache get -> adapter
fetch -> cache put -> ``WeatherContext``.

The entire body is wrapped in ``try/except Exception`` -> log + return
``None``. The caller additionally wraps the whole call in
``asyncio.wait_for(..., timeout=4.0)`` (headroom over the adapter's own
3.0s timeout) -- see ``OutfitPortfolioService._resolve_weather``. This
method can only ever return a ``WeatherContext`` or ``None``. It cannot
raise, and it cannot hang the request.
"""

from __future__ import annotations

import logging

from adapters.interfaces import IWardrobeRepository, IWeatherProvider
from services.app_config import AppConfigService, AppConfigSnapshot
from services.app_config_specs import WEATHER_HEAVY_RAIN_SPEC
from services.india_city_coordinates import resolve_city
from services.weather_cache import WeatherCache
from services.weather_rules import WeatherContext, condition_for_wmo_code, is_heavy_rain

logger = logging.getLogger(__name__)


class WeatherService:
    def __init__(
        self,
        *,
        wardrobe_repo: IWardrobeRepository,
        provider: IWeatherProvider,
        cache: WeatherCache,
        app_config: AppConfigService,
    ) -> None:
        self._wardrobe_repo = wardrobe_repo
        self._provider = provider
        self._cache = cache
        self._app_config = app_config

    async def resolve_for_user(
        self, *, jwt: str, user_id: str, config_snapshot: AppConfigSnapshot
    ) -> WeatherContext | None:
        try:
            raw_city = await self._wardrobe_repo.get_city(jwt=jwt, user_id=user_id)
            city = resolve_city(raw_city)
            if city is None:
                logger.info("weather_skipped_no_city", extra={"user_id": user_id})
                return None

            threshold = self._app_config.read(
                config_snapshot, WEATHER_HEAVY_RAIN_SPEC
            ).precip_mm_per_hour

            cached = await self._cache.get(city.slug)
            if cached is not None:
                return _context_from_cache(city.name, cached, threshold=threshold)

            obs = await self._provider.fetch_current(lat=city.lat, lng=city.lng)
            if obs is None:
                return None

            await self._cache.set(
                city.slug,
                {
                    "temp_c": obs.temp_c,
                    "humidity": obs.humidity,
                    "weather_code": obs.weather_code,
                    "precipitation_mm": obs.precipitation_mm,
                    "observed_at": obs.observed_at,
                },
            )

            heavy = is_heavy_rain(
                weather_code=obs.weather_code,
                precipitation_mm=obs.precipitation_mm,
                precip_threshold_mm_per_hour=threshold,
            )
            return WeatherContext(
                city=city.name,
                temp_c=obs.temp_c,
                condition=condition_for_wmo_code(obs.weather_code),
                humidity=obs.humidity,
                is_heavy_rain=heavy,
                observed_at=obs.observed_at,
            )
        except Exception as exc:  # noqa: BLE001 -- weather must never fail a suggestion request
            logger.warning("weather_resolve_failed", extra={"user_id": user_id, "error": str(exc)})
            return None


def _context_from_cache(city_name: str, cached: dict, *, threshold: float) -> WeatherContext | None:
    try:
        weather_code = int(cached["weather_code"])
        precipitation_mm = float(cached["precipitation_mm"])
        heavy = is_heavy_rain(
            weather_code=weather_code,
            precipitation_mm=precipitation_mm,
            precip_threshold_mm_per_hour=threshold,
        )
        return WeatherContext(
            city=city_name,
            temp_c=float(cached["temp_c"]),
            condition=condition_for_wmo_code(weather_code),
            humidity=int(cached["humidity"]),
            is_heavy_rain=heavy,
            observed_at=str(cached["observed_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("weather_cache_shape_invalid", extra={"error": str(exc)})
        return None
