"""Tests for backend/services/engine_v2_effort_dial.py (SS-039 design's
"Concrete values" #2 and Test plan)."""

from __future__ import annotations

from typing import Any, get_args

from adapters.interfaces import IAppConfigRepository, IRateLimiter, RateLimitDecision
from services.app_config import AppConfigService
from services.app_config_specs import EngineV2EffortTierConfig
from services.cost_budget_gate import CostBudgetGate
from services.engine_v2_effort_dial import (
    BUDGET_NEAR_CEILING_RATIO,
    EffortTierKey,
    both_providers_down,
    is_budget_near_ceiling,
    resolve_effort_tier,
    resolve_effort_tier_for_request,
)
from services.routing_mix_monitor import RoutingMixMonitor


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeConfigRepository(IAppConfigRepository):
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self._values = values or {}

    async def fetch_all(self) -> dict[str, Any]:
        return self._values


class _FakeAtomicLimiter(IRateLimiter):
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        raise AssertionError("budget_status() must never call check_and_consume")

    async def adjust(self, *, key: str, delta: int) -> None:
        raise AssertionError("budget_status() must never call adjust")

    async def peek(self, *, key: str) -> int | None:
        return self.counters.get(key)


class _AssertNotCalledGate(CostBudgetGate):
    """A CostBudgetGate stand-in whose ``budget_status`` raises if invoked
    -- proves the short-circuit in resolve_effort_tier_for_request is real,
    not just a lucky branch order."""

    async def budget_status(self, **kwargs: Any) -> Any:
        raise AssertionError("budget_status() must not be called when providers_down is True")


def _budgets_value() -> dict[str, Any]:
    tier = {"daily_paise": 500, "monthly_paise": 2500, "enforce": True, "fail_open": False}
    return {"free": dict(tier), "premium": dict(tier), "premium_annual": dict(tier)}


async def _config_service_and_snapshot(values: dict[str, Any] | None = None) -> Any:
    service = AppConfigService(_FakeConfigRepository(values))
    snapshot = await service.snapshot()
    return service, snapshot


# --- ConfigSpec defaults / malformed row ---------------------------------


def test_config_spec_defaults_match_ticket_table() -> None:
    config = EngineV2EffortTierConfig()

    assert config.e0.search_pool_size == 500
    assert config.e0.mmr_lambda == 0.9
    assert config.e0.max_exploration == 0
    assert config.e0.llm_candidate_count is None

    assert config.e1.search_pool_size == 1500
    assert config.e1.mmr_lambda == 0.85
    assert config.e1.max_exploration == 0
    assert config.e1.llm_candidate_count == 5

    assert config.e2.search_pool_size == 5000
    assert config.e2.mmr_lambda == 0.75
    assert config.e2.max_exploration == 1
    assert config.e2.llm_candidate_count == 6


async def test_malformed_row_falls_back_to_full_default_not_partial_merge() -> None:
    from services.app_config_specs import ENGINE_V2_EFFORT_TIER_SPEC

    values = {
        "engine_v2_effort_tiers": {
            "e0": {
                "search_pool_size": 500,
                "colour_mode": "star",
                "mmr_lambda": 0.9,
                "max_exploration": 0,
                "llm_candidate_count": None,
            },
            "e1": "not-an-object",
        }
    }
    service = AppConfigService(_FakeConfigRepository(values))
    snapshot = await service.snapshot()

    config = service.read(snapshot, ENGINE_V2_EFFORT_TIER_SPEC)

    default = EngineV2EffortTierConfig()
    assert config == default


# --- resolve_effort_tier() branches --------------------------------------


def test_resolve_effort_tier_providers_down_wins_over_budget() -> None:
    assert resolve_effort_tier(providers_down=True, budget_near_ceiling=True) == "E0"


def test_resolve_effort_tier_providers_down_alone() -> None:
    assert resolve_effort_tier(providers_down=True, budget_near_ceiling=False) == "E0"


def test_resolve_effort_tier_budget_near_ceiling_alone() -> None:
    assert resolve_effort_tier(providers_down=False, budget_near_ceiling=True) == "E1"


def test_resolve_effort_tier_healthy_and_affordable() -> None:
    assert resolve_effort_tier(providers_down=False, budget_near_ceiling=False) == "E2"


# --- both_providers_down() -----------------------------------------------


def test_both_providers_down_true_only_when_both_streaks_exceed_threshold() -> None:
    clock = _FakeClock()
    monitor = RoutingMixMonitor(provider_outage_alert_seconds=900.0, clock=clock)

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Decision:
        provider: str
        cost_class: str = "everyday"

    monitor.record(_Decision("gemini"), "transient")
    clock.advance(1000.0)
    assert both_providers_down(monitor) is False  # only gemini past threshold

    monitor.record(_Decision("claude"), "transient")
    clock.advance(1000.0)
    assert both_providers_down(monitor) is True


def test_both_providers_down_false_on_fresh_monitor() -> None:
    monitor = RoutingMixMonitor()
    assert both_providers_down(monitor) is False


# --- is_budget_near_ceiling() ---------------------------------------------


async def test_is_budget_near_ceiling_true_at_or_above_ratio() -> None:
    limiter = _FakeAtomicLimiter()
    from services.ist_window import ist_day_key

    daily_key = f"stylesense:cost:daily:u1:{ist_day_key()}"
    limiter.counters[daily_key] = 500_000_000  # matches ceiling * ratio below

    service, snapshot = await _config_service_and_snapshot({"ai_cost_budgets": _budgets_value()})
    gate = CostBudgetGate(limiter, service)

    result = await is_budget_near_ceiling(
        gate, user_id="u1", tier="free", config_snapshot=snapshot, near_ceiling_ratio=0.9
    )

    assert result is True


# --- resolve_effort_tier_for_request() short-circuit ----------------------


async def test_resolve_effort_tier_for_request_e0_short_circuits_before_budget_read() -> None:
    clock = _FakeClock()
    monitor = RoutingMixMonitor(provider_outage_alert_seconds=900.0, clock=clock)

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Decision:
        provider: str
        cost_class: str = "everyday"

    for provider in ("gemini", "claude"):
        monitor.record(_Decision(provider), "transient")
    clock.advance(1000.0)

    limiter = _FakeAtomicLimiter()
    service, snapshot = await _config_service_and_snapshot({"ai_cost_budgets": _budgets_value()})
    gate = _AssertNotCalledGate(limiter, service)
    app_config = AppConfigService(_FakeConfigRepository({}))

    tier_key, params = await resolve_effort_tier_for_request(
        monitor=monitor,
        gate=gate,
        user_id="u1",
        tier="free",
        config_snapshot=snapshot,
        app_config=app_config,
    )

    assert tier_key == "E0"
    assert params.mmr_lambda == 0.9


async def test_resolve_effort_tier_for_request_healthy_and_affordable_returns_e2() -> None:
    monitor = RoutingMixMonitor()
    limiter = _FakeAtomicLimiter()
    service, snapshot = await _config_service_and_snapshot({"ai_cost_budgets": _budgets_value()})
    gate = CostBudgetGate(limiter, service)
    app_config = AppConfigService(_FakeConfigRepository({}))

    tier_key, params = await resolve_effort_tier_for_request(
        monitor=monitor,
        gate=gate,
        user_id="u1",
        tier="free",
        config_snapshot=snapshot,
        app_config=app_config,
    )

    assert tier_key == "E2"
    assert params.mmr_lambda == 0.75


# --- E3/E4 structural unreachability (AC #4) -------------------------------


def test_e3_e4_are_structurally_unreachable() -> None:
    assert get_args(EffortTierKey) == ("E0", "E1", "E2")
    # resolve_effort_tier's only two bool inputs cannot produce a fourth
    # value -- the 4 possible (providers_down, budget_near_ceiling)
    # combinations all map onto {"E0", "E1", "E2"}.
    for providers_down in (True, False):
        for budget_near_ceiling in (True, False):
            result = resolve_effort_tier(
                providers_down=providers_down, budget_near_ceiling=budget_near_ceiling
            )
            assert result in ("E0", "E1", "E2")


def test_budget_near_ceiling_ratio_constant_matches_design() -> None:
    assert BUDGET_NEAR_CEILING_RATIO == 0.9


# --- AC #3 integration proof: mmr_lambda/max_exploration produce a real,
# observable per-tier difference (search_pool_size/top_k_bases does NOT,
# see design doc Open Questions #4 / BL-136 -- deliberately not tested here)
# ---------------------------------------------------------------------------


def _build_scored_candidates() -> list[Any]:
    """Runs stage①/②/③ (eligibility, search, scoring) against a wardrobe
    rich enough to produce several assembled candidates, so stage④
    (select_portfolio) has real diversity to work with."""
    from datetime import date

    from services import (
        engine_v2_attribute_scoring,
        engine_v2_candidate_search,
        engine_v2_eligibility,
    )
    from services.app_config import AppConfigSnapshot
    from services.engine_v2_types import NoveltyInputs
    from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput

    as_of = date(2026, 7, 29)
    occasion = OccasionStylingInput(key="office", kind="professional", formality=6)

    tops = [
        WardrobeItemInput(id=f"top{i}", category="western_top", color_primary=color)
        for i, color in enumerate(["#1E3A8A", "#8B0000", "#228B22"])
    ]
    bottoms = [
        WardrobeItemInput(id=f"bottom{i}", category="western_bottom", color_primary=color)
        for i, color in enumerate(["#000000", "#4B4B4B", "#3B2F2F"])
    ]
    footwear = [
        WardrobeItemInput(id=f"shoe{i}", category="footwear_formal", color_primary=color)
        for i, color in enumerate(["#000000", "#5C4033", "#1C1C1C"])
    ]
    wardrobe = tops + bottoms + footwear

    def garment_lookup(category: str) -> None:
        return None  # fallback path -- mirrors test_engine_v2_integration.py's fixtures

    rules = engine_v2_eligibility.resolve_styling_rules(occasion)
    near_white = engine_v2_eligibility.resolve_near_white_thresholds(AppConfigSnapshot(), rules)
    eligibility = engine_v2_eligibility.filter_eligible(
        wardrobe, occasion, rules, near_white_thresholds=near_white
    )
    search_result = engine_v2_candidate_search.search_candidates(
        eligibility.eligible_items,
        occasion=occasion,
        garment_lookup=garment_lookup,
        rules=rules,
        as_of=as_of,
        season=None,
        style_preferences=None,
        top_n_per_remaining_slot=3,
    )
    novelty_inputs = NoveltyInputs(wear_recency_by_item={}, recent_impression_item_counts={})
    scored = [
        engine_v2_attribute_scoring.score_assembled_candidate(
            candidate,
            occasion,
            rules,
            garment_lookup=garment_lookup,
            fabric_attrs={},
            novelty_inputs=novelty_inputs,
            as_of=as_of,
            season=None,
            style_preferences=None,
        )
        for candidate in search_result.candidates
    ]
    return scored


def test_portfolio_diversity_and_size_differ_between_e0_and_e2() -> None:
    from services.engine_v2_portfolio import jaccard_similarity, select_portfolio
    from services.styling_rules_types import GapReport

    scored = _build_scored_candidates()
    assert len(scored) >= 3  # enough real candidates for diversity to matter

    gap_report = GapReport()

    e0_result = select_portfolio(
        scored, lambda_=0.9, max_exploration=0, gap_report=gap_report
    )
    e2_result = select_portfolio(
        scored, lambda_=0.75, max_exploration=1, gap_report=gap_report
    )

    # (a) E2's exploration slot (max_exploration=1) makes its portfolio
    # exactly one member larger than E0's (max_exploration=0), given both
    # ran off the same eligible pool with enough candidates to fill it.
    assert len(e2_result.portfolio) == len(e0_result.portfolio) + 1

    def mean_pairwise_jaccard(portfolio: list[Any]) -> float:
        candidates = [pc.candidate for pc in portfolio]
        if len(candidates) < 2:
            return 0.0
        pairs = [
            jaccard_similarity(candidates[i], candidates[j])
            for i in range(len(candidates))
            for j in range(i + 1, len(candidates))
        ]
        return sum(pairs) / len(pairs)

    # (b) E0's higher lambda (0.9, favours raw score over diversity) yields
    # a portfolio at least as similar internally as E2's (lambda=0.75,
    # favours diversity more).
    e0_diversity = mean_pairwise_jaccard(e0_result.portfolio)
    e2_diversity = mean_pairwise_jaccard(e2_result.portfolio)
    assert e0_diversity >= e2_diversity
