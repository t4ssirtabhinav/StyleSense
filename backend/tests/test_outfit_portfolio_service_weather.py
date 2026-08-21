"""Tests for OutfitPortfolioService's SS-022 weather wiring -- extends
SS-020/023's existing service fakes (test_outfit_portfolio_service.py's own
fixture shapes, duplicated minimally here to keep this file self-contained
per that file's own precedent)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from adapters.interfaces import (
    CachedNarration,
    FabricAttributes,
    GarmentRegistrySnapshot,
    IFabricRegistryRepository,
    IGarmentRegistryRepository,
    ImpressionRef,
    IOccasionRepository,
    IRateLimiter,
    ISuggestionLogRepository,
    ISuggestionNarrationCacheRepository,
    IWardrobeRepository,
    IWearHistoryRepository,
    OccasionRegistrySnapshot,
    RateLimitDecision,
    SuggestionSessionLog,
    WearRecency,
)
from ai.ports.interfaces import NarratedCandidate, NarratedPortfolioResult
from services.app_config import AppConfigService, AppConfigSnapshot
from services.cost_budget_gate import CostBudgetGate
from services.engine_v2 import EngineV2
from services.garment_registry_adapter import GarmentRegistryAdapter
from services.occasion_normalizer import OccasionNormalizer
from services.outfit_portfolio_service import OutfitPortfolioService
from services.provider_quota import ProviderQuotaTracker
from services.routing_mix_monitor import RoutingMixMonitor
from services.suggestion_narration_cache import NarrationCacheOrchestrator
from services.weather_rules import WeatherContext


@pytest.fixture(autouse=True)
def _salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUGGESTION_CACHE_SALT", "test-salt-do-not-use-in-prod")


# ---------------------------------------------------------------------------
# Fakes (minimal, mirrors test_outfit_portfolio_service.py's shapes)
# ---------------------------------------------------------------------------


class _FakeWardrobeRepo(IWardrobeRepository):
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows if rows is not None else []

    async def upsert_uploaded_row(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def update_bg_removal_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        return "free"

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
        return self._rows

    # SS-048 mechanical addition: same ABC-extension trap as the SS-022 note
    # below -- IWardrobeRepository grew a new abstract method, every fake
    # implementing it must add a stub or the class can't be instantiated.
    async def get_items_for_rails(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        return None

    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        return "Mumbai"


class _FakeOccasionRepo(IOccasionRepository):
    def __init__(self, snapshot: OccasionRegistrySnapshot) -> None:
        self._snapshot = snapshot

    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        return self._snapshot


class _FakeGarmentRegistryRepo(IGarmentRegistryRepository):
    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        return GarmentRegistrySnapshot(rows={}, aliases={})


class _FakeFabricRepo(IFabricRegistryRepository):
    async def fetch_all(self) -> dict[str, FabricAttributes]:
        return {}


class _FakeWearHistoryRepo(IWearHistoryRepository):
    async def fetch_wear_recency(
        self, *, jwt: str, user_id: str, occasion_key: str | None = None
    ) -> list[WearRecency]:
        return []


class _FakeSuggestionLogRepo(ISuggestionLogRepository):
    def __init__(self) -> None:
        self.logged_sessions: list[Any] = []

    async def log_session(self, session: SuggestionSessionLog, impressions: Any) -> str | None:
        self.logged_sessions.append((session, list(impressions)))
        return "session-1"

    async def log_outcome(self, outcome: Any) -> str | None:
        return None

    async def recent_impressions(self, *, user_id: str, since: Any, limit: int = 200) -> list[dict]:
        return []

    async def update_session_outcome(self, **kwargs: Any) -> None:
        pass

    async def find_impression(self, *, session_id: str, rank: int) -> ImpressionRef | None:
        return None


class _FakeNarrationCacheRepo(ISuggestionNarrationCacheRepository):
    def __init__(self, hit: CachedNarration | None = None) -> None:
        self._hit = hit
        self.get_calls = 0
        self.put_calls: list[dict[str, Any]] = []
        self.last_signature_hash: str | None = None

    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        self.get_calls += 1
        self.last_signature_hash = signature_hash
        return self._hit

    async def put(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)


class _FakeRateLimiter(IRateLimiter):
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        current = self.counters.get(key, 0) + amount
        self.counters[key] = current
        allowed = current <= ceiling
        if not allowed:
            self.counters[key] = current - amount
        return RateLimitDecision(allowed=allowed, current=current, ceiling=ceiling, degraded=False)

    async def adjust(self, *, key: str, delta: int) -> None:
        self.counters[key] = self.counters.get(key, 0) + delta

    async def peek(self, *, key: str) -> int | None:
        return self.counters.get(key)


class _FakeMetrics:
    def __init__(self) -> None:
        self.provider = "gemini"
        self.model = "gemini-3.1-flash-lite"
        self.tokens_in = 100
        self.tokens_out = 50
        self.latency_ms = 5
        self.attempt = 1


class _FakeStylingProvider:
    def __init__(self, narrations: list[NarratedCandidate], *, source: str = "gemini") -> None:
        self._narrations = narrations
        self._source = source
        self.call_count = 0
        self.last_weather: dict[str, Any] | None = None

    async def suggest_outfits_with_metrics(
        self, preferences: Any, *, max_suggestions: int = 5
    ) -> Any:
        raise NotImplementedError

    async def narrate_candidates_with_metrics(
        self,
        candidates: list[dict[str, Any]],
        *,
        occasion: str,
        preferences: Any,
        max_suggestions: int,
        weather: dict[str, Any] | None = None,
    ) -> tuple[NarratedPortfolioResult, _FakeMetrics]:
        self.call_count += 1
        self.last_weather = weather
        result = NarratedPortfolioResult(
            narrations=self._narrations[:max_suggestions],
            language="en",
            source=self._source,  # type: ignore[arg-type]
        )
        return result, _FakeMetrics()


class _FakeRegistry:
    def __init__(self, provider: _FakeStylingProvider) -> None:
        self._provider = provider

    def get(self, provider: str, model: str) -> Any:
        return self._provider


class _FakeWeatherService:
    def __init__(self, weather: WeatherContext | None = None, *, raises: bool = False) -> None:
        self._weather = weather
        self._raises = raises
        self.calls = 0

    async def resolve_for_user(
        self, *, jwt: str, user_id: str, config_snapshot: AppConfigSnapshot
    ) -> WeatherContext | None:
        self.calls += 1
        if self._raises:
            raise RuntimeError("weather service exploded")
        return self._weather


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _item_row(id: str, *, category: str = "western_top", color: str = "#1E3A8A") -> dict[str, Any]:
    return {"id": id, "category": category, "color_primary": color}


def _wardrobe_rows() -> list[dict[str, Any]]:
    return [
        _item_row("top1", category="western_top", color="#1E3A8A"),
        _item_row("bottom1", category="western_bottom", color="#1E3A8A"),
        _item_row("shoe1", category="footwear_casual", color="#000000"),
    ]


def _occasion_snapshot() -> OccasionRegistrySnapshot:
    return OccasionRegistrySnapshot(
        keys=("office",),
        aliases={},
        labels={"office": "Office"},
        badge_colors={"office": "office"},
        kinds={"office": "professional"},
        formalities={"office": 6},
        styling_rules={"office": {}},
    )


def _dummy_app_config() -> AppConfigService:
    from adapters.interfaces import IAppConfigRepository

    class _EmptyConfigRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict[str, Any]:
            return {}

    return AppConfigService(_EmptyConfigRepo())


def _empty_snapshot() -> AppConfigSnapshot:
    return AppConfigSnapshot(values={}, fetched_at=time.monotonic(), stale=False)


def _weather(
    *, temp_c: float = 28.4, condition: str = "partly_cloudy", is_heavy: bool = False
) -> WeatherContext:
    return WeatherContext(
        city="Mumbai",
        temp_c=temp_c,
        condition=condition,  # type: ignore[arg-type]
        humidity=71,
        is_heavy_rain=is_heavy,
        observed_at="2026-08-14T13:00",
    )


def _build_service(
    *,
    weather_service: Any,
    styling_provider: _FakeStylingProvider,
    log_repo: _FakeSuggestionLogRepo | None = None,
    narration_cache_repo: _FakeNarrationCacheRepo | None = None,
    rate_limiter: _FakeRateLimiter | None = None,
) -> tuple[OutfitPortfolioService, _FakeSuggestionLogRepo, _FakeNarrationCacheRepo]:
    log_repo = log_repo or _FakeSuggestionLogRepo()
    narration_cache_repo = narration_cache_repo or _FakeNarrationCacheRepo()
    rate_limiter = rate_limiter or _FakeRateLimiter()
    occasion_normalizer = OccasionNormalizer(_FakeOccasionRepo(_occasion_snapshot()))
    app_config = _dummy_app_config()
    engine = EngineV2(
        garment_registry=GarmentRegistryAdapter(_FakeGarmentRegistryRepo()),
        fabric_repo=_FakeFabricRepo(),
        wear_history_repo=_FakeWearHistoryRepo(),
        suggestion_log_repo=log_repo,
        app_config=app_config,
    )
    service = OutfitPortfolioService(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        occasion_normalizer=occasion_normalizer,
        engine=engine,
        app_config=app_config,
        routing_mix_monitor=RoutingMixMonitor(),
        cost_budget_gate=CostBudgetGate(rate_limiter, app_config),
        provider_registry=_FakeRegistry(styling_provider),
        provider_quota=ProviderQuotaTracker(),
        narration_cache=NarrationCacheOrchestrator(narration_cache_repo),
        suggestion_log_repo=log_repo,
        weather_service=weather_service,
    )
    return service, log_repo, narration_cache_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_weather_present_flows_to_engine_signature_prompt_and_response() -> None:
    weather = _weather()
    weather_service = _FakeWeatherService(weather)
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    service, _log_repo, cache_repo = _build_service(
        weather_service=weather_service, styling_provider=provider
    )

    result = await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    assert weather_service.calls == 1
    assert result["weather"] == weather.model_dump()
    # The narration path received the weather dict.
    assert provider.last_weather == weather.model_dump()
    # The cache signature was computed with a non-"none" bucket.
    assert cache_repo.last_signature_hash is not None


async def test_weather_none_produces_ss023_baseline_shape() -> None:
    weather_service = _FakeWeatherService(None)
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    service, _log_repo, _cache_repo = _build_service(
        weather_service=weather_service, styling_provider=provider
    )

    result = await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    assert result["weather"] is None
    assert provider.last_weather is None
    assert "portfolio" in result
    assert "gap_report" in result
    assert result["gap_report"]["weather_exclusions_relaxed"] is False


async def test_weather_service_raising_degrades_to_full_200_payload_weather_none() -> None:
    """The headline degradation test."""
    weather_service = _FakeWeatherService(raises=True)
    provider = _FakeStylingProvider([])
    service, _log_repo, _cache_repo = _build_service(
        weather_service=weather_service, styling_provider=provider
    )

    result = await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    assert result["weather"] is None
    assert "portfolio" in result


async def test_different_temperature_bands_produce_different_signature_hashes() -> None:
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    cache_repo_a = _FakeNarrationCacheRepo()
    service_a, _, _ = _build_service(
        weather_service=_FakeWeatherService(_weather(temp_c=28.0)),
        styling_provider=provider,
        narration_cache_repo=cache_repo_a,
    )
    await service_a.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    provider2 = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    cache_repo_b = _FakeNarrationCacheRepo()
    service_b, _, _ = _build_service(
        weather_service=_FakeWeatherService(_weather(temp_c=5.0)),
        styling_provider=provider2,
        narration_cache_repo=cache_repo_b,
    )
    await service_b.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    assert cache_repo_a.last_signature_hash != cache_repo_b.last_signature_hash


async def test_same_temperature_band_produces_same_signature_hash() -> None:
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    cache_repo_a = _FakeNarrationCacheRepo()
    service_a, _, _ = _build_service(
        weather_service=_FakeWeatherService(_weather(temp_c=28.0)),
        styling_provider=provider,
        narration_cache_repo=cache_repo_a,
    )
    await service_a.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    provider2 = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    cache_repo_b = _FakeNarrationCacheRepo()
    service_b, _, _ = _build_service(
        weather_service=_FakeWeatherService(_weather(temp_c=29.0)),
        styling_provider=provider2,
        narration_cache_repo=cache_repo_b,
    )
    await service_b.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )

    assert cache_repo_a.last_signature_hash == cache_repo_b.last_signature_hash
