"""Tests for backend/services/weather_service.py (SS-022), fakes for
repo/cache/provider -- no real network/DB/Redis calls."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from adapters.interfaces import IAppConfigRepository, IWardrobeRepository, WeatherObservation
from services.app_config import AppConfigService, AppConfigSnapshot
from services.weather_service import WeatherService


class _FakeWardrobeRepo(IWardrobeRepository):
    def __init__(self, city: str | None) -> None:
        self._city = city

    async def upsert_uploaded_row(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def update_bg_removal_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        raise NotImplementedError

    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        raise NotImplementedError

    async def update_tagging_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_item_image_info(self, *, jwt: str, item_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_items_image_info_bulk(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        raise NotImplementedError

    async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    # SS-048 mechanical addition: same ABC-extension trap as the SS-022 note
    # below -- IWardrobeRepository grew a new abstract method, every fake
    # implementing it must add a stub or the class can't be instantiated.
    async def get_items_for_rails(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        return self._city


class _RaisingWardrobeRepo(_FakeWardrobeRepo):
    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        raise RuntimeError("db unreachable")


class _FakeProvider:
    def __init__(self, obs: WeatherObservation | None, *, sleep_seconds: float = 0.0) -> None:
        self._obs = obs
        self._sleep_seconds = sleep_seconds
        self.call_count = 0

    async def fetch_current(self, *, lat: float, lng: float) -> WeatherObservation | None:
        self.call_count += 1
        if self._sleep_seconds:
            await asyncio.sleep(self._sleep_seconds)
        return self._obs


class _RaisingProvider:
    async def fetch_current(self, *, lat: float, lng: float) -> WeatherObservation | None:
        raise RuntimeError("provider exploded")


class _FakeCache:
    def __init__(self, hit: dict[str, Any] | None = None) -> None:
        self._hit = hit
        self.get_calls = 0
        self.set_calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, city_slug: str) -> dict[str, Any] | None:
        self.get_calls += 1
        return self._hit

    async def set(self, city_slug: str, payload: dict[str, Any]) -> None:
        self.set_calls.append((city_slug, payload))


class _RaisingCache:
    async def get(self, city_slug: str) -> dict[str, Any] | None:
        raise RuntimeError("cache unreachable")

    async def set(self, city_slug: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("cache unreachable")


def _dummy_app_config() -> AppConfigService:
    class _EmptyConfigRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict[str, Any]:
            return {}

    return AppConfigService(_EmptyConfigRepo())


def _empty_snapshot() -> AppConfigSnapshot:
    return AppConfigSnapshot(values={}, fetched_at=time.monotonic(), stale=False)


def _obs(*, weather_code: int = 3, precipitation_mm: float = 0.0) -> WeatherObservation:
    return WeatherObservation(
        temp_c=28.2,
        humidity=79,
        weather_code=weather_code,
        precipitation_mm=precipitation_mm,
        observed_at="2026-08-14T10:45",
    )


@pytest.mark.parametrize("city", [None, "", "Springfield"])
async def test_no_city_or_unresolvable_city_returns_none_provider_never_called(
    city: str | None,
) -> None:
    provider = _FakeProvider(_obs())
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo(city),
        provider=provider,  # type: ignore[arg-type]
        cache=_FakeCache(),  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is None
    assert provider.call_count == 0


async def test_cache_hit_provider_never_called() -> None:
    provider = _FakeProvider(_obs())
    cache = _FakeCache(
        hit={
            "temp_c": 28.2,
            "humidity": 79,
            "weather_code": 3,
            "precipitation_mm": 0.0,
            "observed_at": "2026-08-14T10:00",
        }
    )
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo("Mumbai"),
        provider=provider,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is not None
    assert result.city == "Mumbai"
    assert provider.call_count == 0


async def test_cache_miss_provider_called_once_and_written_back() -> None:
    provider = _FakeProvider(_obs())
    cache = _FakeCache(hit=None)
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo("Mumbai"),
        provider=provider,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is not None
    assert provider.call_count == 1
    assert len(cache.set_calls) == 1
    assert cache.set_calls[0][0] == "mumbai"


async def test_provider_returns_none_service_returns_none_and_nothing_cached() -> None:
    provider = _FakeProvider(None)
    cache = _FakeCache(hit=None)
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo("Mumbai"),
        provider=provider,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is None
    assert cache.set_calls == []


async def test_repository_raising_degrades_to_none() -> None:
    service = WeatherService(
        wardrobe_repo=_RaisingWardrobeRepo("Mumbai"),
        provider=_FakeProvider(_obs()),  # type: ignore[arg-type]
        cache=_FakeCache(),  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is None


async def test_cache_raising_degrades_to_none() -> None:
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo("Mumbai"),
        provider=_FakeProvider(_obs()),  # type: ignore[arg-type]
        cache=_RaisingCache(),  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is None


async def test_provider_raising_degrades_to_none() -> None:
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo("Mumbai"),
        provider=_RaisingProvider(),  # type: ignore[arg-type]
        cache=_FakeCache(hit=None),  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    result = await service.resolve_for_user(
        jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()
    )
    assert result is None


async def test_provider_timeout_degrades_to_none_within_bound() -> None:
    """asyncio timeout test, not a wall-clock sleep in CI -- the caller
    (OutfitPortfolioService._resolve_weather) wraps resolve_for_user in
    asyncio.wait_for(timeout=4.0); this pins that a slow provider inside a
    bounded outer timeout degrades to None rather than hanging."""
    provider = _FakeProvider(_obs(), sleep_seconds=10.0)
    service = WeatherService(
        wardrobe_repo=_FakeWardrobeRepo("Mumbai"),
        provider=provider,  # type: ignore[arg-type]
        cache=_FakeCache(hit=None),  # type: ignore[arg-type]
        app_config=_dummy_app_config(),
    )
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            service.resolve_for_user(jwt="jwt", user_id="u1", config_snapshot=_empty_snapshot()),
            timeout=0.05,
        )
