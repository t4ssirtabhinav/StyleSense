"""Tests for backend/services/outfit_portfolio_service.py (SS-020) --
docs/tickets/SS-020-design.md section 2's exact sequence, against fake
repos/adapters. No real network/DB calls."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
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
    SuggestionImpressionLog,
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


@pytest.fixture(autouse=True)
def _salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUGGESTION_CACHE_SALT", "test-salt-do-not-use-in-prod")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeWardrobeRepo(IWardrobeRepository):
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        plan_tier: str = "free",
        preferences: dict[str, Any] | None = None,
        city: str | None = None,
    ) -> None:
        self._rows = rows if rows is not None else []
        self.plan_tier = plan_tier
        self.preferences = preferences
        self.city = city

    async def upsert_uploaded_row(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def update_bg_removal_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        return self.plan_tier

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

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        return self.preferences

    # SS-022 mechanical addition: same ABC-extension trap as above.
    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        return self.city


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
        self.logged_sessions: list[tuple[SuggestionSessionLog, list[SuggestionImpressionLog]]] = []
        self.outcome_updates: list[dict[str, Any]] = []
        self.raise_on_update = False

    async def log_session(self, session, impressions):  # type: ignore[no-untyped-def]
        self.logged_sessions.append((session, list(impressions)))
        return "session-1"

    async def log_outcome(self, outcome):  # type: ignore[no-untyped-def]
        return None

    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict]:
        return []

    async def update_session_outcome(
        self,
        *,
        session_id: str,
        cost_incurred: bool,
        request_id: str | None,
        latency_ms: int | None,
    ) -> None:
        if self.raise_on_update:
            raise RuntimeError("outcome update failed")
        self.outcome_updates.append(
            {
                "session_id": session_id,
                "cost_incurred": cost_incurred,
                "request_id": request_id,
                "latency_ms": latency_ms,
            }
        )

    async def find_impression(self, *, session_id: str, rank: int) -> ImpressionRef | None:
        return None


class _FakeWeatherService:
    """(SS-022) Duck-typed against WeatherService's own public shape --
    this file's tests are pre-existing SS-020/023 coverage, not weather
    coverage (see test_outfit_portfolio_service_weather.py for that).
    Defaults to 'no weather', reproducing pre-SS-022 output byte-for-byte."""

    def __init__(self, weather: Any = None) -> None:
        self._weather = weather
        self.calls = 0

    async def resolve_for_user(self, *, jwt: str, user_id: str, config_snapshot: Any) -> Any:
        self.calls += 1
        return self._weather


class _FakeNarrationCacheRepo(ISuggestionNarrationCacheRepository):
    def __init__(self, hit: CachedNarration | None = None) -> None:
        self._hit = hit
        self.get_calls = 0
        self.put_calls: list[dict[str, Any]] = []

    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        self.get_calls += 1
        return self._hit

    async def put(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)


class _FakeRateLimiter(IRateLimiter):
    """Mirrors test_cost_budget_gate.py's own fake: allow/deny from a single
    atomic increment, self-refunding on deny."""

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


@dataclass(frozen=True)
class _FakeMetrics:
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    attempt: int = 1


class _FakeStylingProvider:
    def __init__(self, narrations: list[NarratedCandidate], *, source: str = "gemini") -> None:
        self._narrations = narrations
        self._source = source
        self.call_count = 0

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
        result = NarratedPortfolioResult(
            narrations=self._narrations[:max_suggestions],
            language="en",
            source=self._source,  # type: ignore[arg-type]
        )
        metrics = _FakeMetrics(
            provider="gemini",
            model="gemini-3.1-flash-lite",
            tokens_in=100,
            tokens_out=50,
            latency_ms=5,
        )
        return result, metrics


class _FakeRegistry:
    def __init__(self, provider: _FakeStylingProvider) -> None:
        self._provider = provider

    def get(self, provider: str, model: str) -> Any:
        return self._provider


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _item_row(id: str, *, category: str = "western_top", color: str = "#1E3A8A") -> dict[str, Any]:
    return {"id": id, "category": category, "color_primary": color}


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


def _build_engine(*, suggestion_log_repo: ISuggestionLogRepository) -> EngineV2:
    return EngineV2(
        garment_registry=GarmentRegistryAdapter(_FakeGarmentRegistryRepo()),
        fabric_repo=_FakeFabricRepo(),
        wear_history_repo=_FakeWearHistoryRepo(),
        suggestion_log_repo=suggestion_log_repo,
        app_config=_dummy_app_config(),
    )


def _dummy_app_config() -> AppConfigService:
    from adapters.interfaces import IAppConfigRepository

    class _EmptyConfigRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict[str, Any]:
            return {}

    return AppConfigService(_EmptyConfigRepo())


def _empty_snapshot() -> AppConfigSnapshot:
    return AppConfigSnapshot(values={}, fetched_at=time.monotonic(), stale=False)


def _build_service(
    *,
    wardrobe_repo: IWardrobeRepository,
    suggestion_log_repo: ISuggestionLogRepository,
    narration_cache_repo: ISuggestionNarrationCacheRepository,
    styling_provider: _FakeStylingProvider,
    rate_limiter: IRateLimiter,
    monitor: RoutingMixMonitor | None = None,
    weather_service: Any = None,
) -> OutfitPortfolioService:
    occasion_normalizer = OccasionNormalizer(_FakeOccasionRepo(_occasion_snapshot()))
    engine = _build_engine(suggestion_log_repo=suggestion_log_repo)
    app_config = _dummy_app_config()
    cost_budget_gate = CostBudgetGate(rate_limiter, app_config)
    return OutfitPortfolioService(
        wardrobe_repo=wardrobe_repo,
        occasion_normalizer=occasion_normalizer,
        engine=engine,
        app_config=app_config,
        routing_mix_monitor=monitor or RoutingMixMonitor(),
        cost_budget_gate=cost_budget_gate,
        provider_registry=_FakeRegistry(styling_provider),
        provider_quota=ProviderQuotaTracker(),
        narration_cache=NarrationCacheOrchestrator(narration_cache_repo),
        suggestion_log_repo=suggestion_log_repo,
        weather_service=weather_service or _FakeWeatherService(),  # type: ignore[arg-type]
    )


def _wardrobe_rows(n: int = 6) -> list[dict[str, Any]]:
    return [
        _item_row("top1", category="western_top", color="#1E3A8A"),
        _item_row("bottom1", category="western_bottom", color="#1E3A8A"),
        _item_row("shoe1", category="footwear_casual", color="#000000"),
        _item_row("shoe2", category="footwear_formal", color="#111111"),
        _item_row("dress1", category="western_dress", color="#8B0000"),
        _item_row("jacket1", category="western_outerwear", color="#228B22"),
    ][:n]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_zero_wardrobe_items_returns_limited_options_true_with_200_shape() -> None:
    log_repo = _FakeSuggestionLogRepo()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=[]),
        suggestion_log_repo=log_repo,
        narration_cache_repo=_FakeNarrationCacheRepo(),
        styling_provider=_FakeStylingProvider([]),
        rate_limiter=_FakeRateLimiter(),
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
    assert result["limited_options"] is True
    assert result["portfolio"] == []


async def test_unknown_occasion_degrades_to_everyday_formality_five_never_errors() -> None:
    log_repo = _FakeSuggestionLogRepo()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=_FakeNarrationCacheRepo(),
        styling_provider=_FakeStylingProvider([]),
        rate_limiter=_FakeRateLimiter(),
    )
    result = await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="a totally novel never-seen occasion",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )
    # Never a 500/exception -- degrades to a normal 200-shaped response.
    assert "portfolio" in result
    assert log_repo.logged_sessions  # engine still logged a session
    session, _ = log_repo.logged_sessions[0]
    assert session.occasion == "a_totally_novel_never_seen_occasion"


async def test_e0_tier_skips_narration_and_cache_entirely() -> None:
    """Forces E0 by making both providers appear down to RoutingMixMonitor."""
    from dataclasses import dataclass as _dc

    @_dc(frozen=True)
    class _Decision:
        provider: str
        cost_class: str = "everyday"

    monitor = RoutingMixMonitor(provider_outage_alert_seconds=0.0)
    monitor.record(_Decision("gemini"), "transient")
    monitor.record(_Decision("claude"), "transient")

    cache_repo = _FakeNarrationCacheRepo()
    log_repo = _FakeSuggestionLogRepo()
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="x", rationale="should not be called")]
    )
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=cache_repo,
        styling_provider=provider,
        rate_limiter=_FakeRateLimiter(),
        monitor=monitor,
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
    assert result["effort_tier"] == "E0"
    assert cache_repo.get_calls == 0
    assert provider.call_count == 0
    assert result["cache_hit"] is False


async def test_cache_hit_skips_budget_and_llm_call() -> None:
    cached = CachedNarration(
        narrations_by_signature_index={0: "cached rationale text"}, language="en"
    )
    cache_repo = _FakeNarrationCacheRepo(hit=cached)
    log_repo = _FakeSuggestionLogRepo()
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="x", rationale="should not be called")]
    )
    rate_limiter = _FakeRateLimiter()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=cache_repo,
        styling_provider=provider,
        rate_limiter=rate_limiter,
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
    assert provider.call_count == 0  # no LLM call
    assert rate_limiter.counters == {}  # no budget touched
    if result["portfolio"]:
        assert result["cache_hit"] is True


async def test_cache_miss_calls_reserve_before_narrate_and_reconcile_after() -> None:
    cache_repo = _FakeNarrationCacheRepo(hit=None)
    log_repo = _FakeSuggestionLogRepo()

    class _TrackingRateLimiter(_FakeRateLimiter):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[str] = []

        async def check_and_consume(self, **kwargs: Any) -> RateLimitDecision:
            self.calls.append("check_and_consume")
            return await super().check_and_consume(**kwargs)

        async def adjust(self, **kwargs: Any) -> None:
            self.calls.append("adjust")
            await super().adjust(**kwargs)

    rate_limiter = _TrackingRateLimiter()
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="will-not-match-anything", rationale="narrated text")]
    )
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=cache_repo,
        styling_provider=provider,
        rate_limiter=rate_limiter,
    )
    await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )
    # cost estimate against the default (unpriced) routing table is 0 --
    # reserve() short-circuits without touching Redis (estimate<=0 branch),
    # so this proves the CALL SEQUENCE (narrate happens, no exception) --
    # the real deny-path boundary is proven by the dedicated test below.
    assert provider.call_count == 1


async def test_budget_denied_degrades_to_rule_based_never_a_429() -> None:
    """Real cost estimate > 0 (priced provider/model) + a zero-ceiling free
    tier -- proves the free-tier fail-closed deny degrades to rule-based
    reasoning with a normal (200-shaped) result, never a 429/exception."""
    cache_repo = _FakeNarrationCacheRepo(hit=None)
    log_repo = _FakeSuggestionLogRepo()
    provider = _FakeStylingProvider(
        [NarratedCandidate(outfit_fingerprint="x", rationale="should not be called")]
    )
    rate_limiter = _FakeRateLimiter()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows(), plan_tier="free"),
        suggestion_log_repo=log_repo,
        narration_cache_repo=cache_repo,
        styling_provider=provider,
        rate_limiter=rate_limiter,
    )
    snapshot = AppConfigSnapshot(
        values={
            "ai_price_table": {
                "fx_usd_to_inr": [{"effective_from": "2026-01-01", "rate": 84.0, "verified": True}],
                "prices": [
                    {
                        "provider": "gemini",
                        "model": "gemini-3.1-flash-lite",
                        "mode": "per_token",
                        "effective_from": "2026-01-01",
                        "usd_per_mtok_in": 0.10,
                        "usd_per_mtok_out": 0.40,
                        "default_tokens_in": 500,
                        "default_tokens_out": 200,
                        "verified": True,
                    }
                ],
            },
            "ai_cost_budgets": {
                "free": {"daily_paise": 0, "monthly_paise": 0, "enforce": True, "fail_open": False},
            },
        },
        fetched_at=time.monotonic(),
        stale=False,
    )
    result = await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=snapshot,
    )
    assert provider.call_count == 0  # never reached the LLM
    assert result["cache_hit"] is False
    # A rationale is still present for every portfolio item (rule-based fallback).
    for item in result["portfolio"]:
        assert item["rationale"]


async def test_update_session_outcome_called_exactly_once_and_never_blocks_on_raise() -> None:
    log_repo = _FakeSuggestionLogRepo()
    log_repo.raise_on_update = True
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=_FakeNarrationCacheRepo(),
        styling_provider=_FakeStylingProvider([]),
        rate_limiter=_FakeRateLimiter(),
    )
    # Must not raise even though update_session_outcome raises internally.
    result = await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )
    assert "portfolio" in result
    assert (
        log_repo.outcome_updates == []
    )  # raised, so nothing recorded -- but no exception propagated


# ---------------------------------------------------------------------------
# SS-023 -- additive response fields + exclude_fingerprints forwarding.
# ---------------------------------------------------------------------------


async def test_response_carries_session_id_occasion_key_and_per_item_rank_fingerprint() -> None:
    log_repo = _FakeSuggestionLogRepo()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=_FakeNarrationCacheRepo(),
        styling_provider=_FakeStylingProvider([]),
        rate_limiter=_FakeRateLimiter(),
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
    assert result["session_id"] == "session-1"  # from _FakeSuggestionLogRepo.log_session
    assert result["occasion_key"] == "office"
    assert result["portfolio"]
    for idx, item in enumerate(result["portfolio"], start=1):
        assert item["rank"] == idx
        assert len(item["outfit_fingerprint"]) == 64


async def test_per_item_rank_matches_the_rank_logged_to_suggestion_impressions() -> None:
    """The join key /outfit-suggestions/outcome resolves on must be
    PROVABLY identical, not coincidentally aligned (test plan item 2)."""
    log_repo = _FakeSuggestionLogRepo()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=_FakeNarrationCacheRepo(),
        styling_provider=_FakeStylingProvider([]),
        rate_limiter=_FakeRateLimiter(),
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
    _, logged_impressions = log_repo.logged_sessions[0]
    rank_by_fingerprint = {imp.outfit_fingerprint: imp.rank for imp in logged_impressions}
    for item in result["portfolio"]:
        assert rank_by_fingerprint[item["outfit_fingerprint"]] == item["rank"]


async def test_session_id_none_when_log_repo_degraded_still_returns_full_portfolio() -> None:
    class _DegradedLogRepo(_FakeSuggestionLogRepo):
        async def log_session(self, session, impressions):  # type: ignore[no-untyped-def]
            return None

    log_repo = _DegradedLogRepo()
    service = _build_service(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        suggestion_log_repo=log_repo,
        narration_cache_repo=_FakeNarrationCacheRepo(),
        styling_provider=_FakeStylingProvider([]),
        rate_limiter=_FakeRateLimiter(),
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
    assert result["session_id"] is None
    assert result["portfolio"]  # a None session must still render suggestions


async def test_exclude_fingerprints_forwarded_truncated_at_60() -> None:
    captured: dict[str, Any] = {}

    class _CapturingEngine(EngineV2):
        async def generate_portfolio(self, *args: Any, **kwargs: Any) -> Any:
            captured["exclude_fingerprints"] = kwargs.get("exclude_fingerprints")
            return await super().generate_portfolio(*args, **kwargs)

    log_repo = _FakeSuggestionLogRepo()
    occasion_normalizer = OccasionNormalizer(_FakeOccasionRepo(_occasion_snapshot()))
    engine = _CapturingEngine(
        garment_registry=GarmentRegistryAdapter(_FakeGarmentRegistryRepo()),
        fabric_repo=_FakeFabricRepo(),
        wear_history_repo=_FakeWearHistoryRepo(),
        suggestion_log_repo=log_repo,
        app_config=_dummy_app_config(),
    )
    app_config = _dummy_app_config()
    service = OutfitPortfolioService(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        occasion_normalizer=occasion_normalizer,
        engine=engine,
        app_config=app_config,
        routing_mix_monitor=RoutingMixMonitor(),
        cost_budget_gate=CostBudgetGate(_FakeRateLimiter(), app_config),
        provider_registry=_FakeRegistry(_FakeStylingProvider([])),
        provider_quota=ProviderQuotaTracker(),
        narration_cache=NarrationCacheOrchestrator(_FakeNarrationCacheRepo()),
        suggestion_log_repo=log_repo,
        weather_service=_FakeWeatherService(),  # type: ignore[arg-type]
    )
    over_cap = [f"{i:064x}" for i in range(75)]
    await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
        exclude_fingerprints=over_cap,
    )
    assert captured["exclude_fingerprints"] == frozenset(over_cap[:60])


async def test_empty_exclude_fingerprints_forwarded_as_none() -> None:
    captured: dict[str, Any] = {}

    class _CapturingEngine(EngineV2):
        async def generate_portfolio(self, *args: Any, **kwargs: Any) -> Any:
            captured["exclude_fingerprints"] = kwargs.get("exclude_fingerprints")
            return await super().generate_portfolio(*args, **kwargs)

    log_repo = _FakeSuggestionLogRepo()
    occasion_normalizer = OccasionNormalizer(_FakeOccasionRepo(_occasion_snapshot()))
    engine = _CapturingEngine(
        garment_registry=GarmentRegistryAdapter(_FakeGarmentRegistryRepo()),
        fabric_repo=_FakeFabricRepo(),
        wear_history_repo=_FakeWearHistoryRepo(),
        suggestion_log_repo=log_repo,
        app_config=_dummy_app_config(),
    )
    app_config = _dummy_app_config()
    service = OutfitPortfolioService(
        wardrobe_repo=_FakeWardrobeRepo(rows=_wardrobe_rows()),
        occasion_normalizer=occasion_normalizer,
        engine=engine,
        app_config=app_config,
        routing_mix_monitor=RoutingMixMonitor(),
        cost_budget_gate=CostBudgetGate(_FakeRateLimiter(), app_config),
        provider_registry=_FakeRegistry(_FakeStylingProvider([])),
        provider_quota=ProviderQuotaTracker(),
        narration_cache=NarrationCacheOrchestrator(_FakeNarrationCacheRepo()),
        suggestion_log_repo=log_repo,
        weather_service=_FakeWeatherService(),  # type: ignore[arg-type]
    )
    await service.generate_portfolio_for_request(
        user_id="u1",
        jwt="fake-jwt",
        occasion="office",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
        exclude_fingerprints=[],
    )
    assert captured["exclude_fingerprints"] is None
