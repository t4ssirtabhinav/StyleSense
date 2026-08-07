"""SS-020 manual latency-proof script (Developer phase).

Exercises the AC's own literal wording ("cold call under 4s") the same way
`BL-058`/`BL-067` were verified -- a REAL call, never a synthetic 1-item
wardrobe or a timeout-config assertion. Per `BL-100`'s 2026-07-30 resolution
("happy-path-only"), this proves the single-provider-call path, not the
failover/degrade ladder.

Runs `OutfitPortfolioService.generate_portfolio_for_request` end-to-end
against:
  - a synthetic ~45-item wardrobe (non-trivial, per the design doc's own
    ">=40 items" instruction)
  - a COLD narration cache (in-memory fake that always misses)
  - E2 effort tier (empty budget/monitor state naturally resolves here --
    see `engine_v2_effort_dial.resolve_effort_tier`)
  - `occasion="wedding_guest"`, which `ai_routing_specs.DEFAULT_ROUTING_TABLE`
    routes to `claude`/`HIGH_STAKES_MODEL_ID` (`claude-sonnet-5`) -- the
    SLOWEST model in the live routing table (Claude Sonnet 5 vs
    Gemini 2.5 Flash Lite), per the design doc's own instruction to test
    against the slowest live-routed model.

Only `OutfitPortfolioService`'s own DB-backed collaborators (wardrobe repo,
occasion repo, cost-budget rate limiter, narration cache, suggestion log)
are faked -- these are NOT the thing under test (this repo has no local
Supabase instance running in this environment, and the AC is about AI
provider latency, not DB round-trip latency, which every other ticket's
manual scripts already treat as a separate concern). The narration call
itself -- the dominant cost in the whole request -- goes to the REAL
Anthropic API via a REAL `ClaudeStylingAdapter`, using the real
`ANTHROPIC_API_KEY`.

Usage: `python -m scripts.ss020_verify_latency` (from backend/, with the
venv active and ANTHROPIC_API_KEY set, e.g. via
`set -a && source ../.env && set +a`).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Sequence
from typing import Any

from adapters.interfaces import (
    CachedNarration,
    FabricAttributes,
    GarmentRegistrySnapshot,
    IFabricRegistryRepository,
    IGarmentRegistryRepository,
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
from ai.adapters.claude_styling_adapter import ClaudeStylingAdapter
from ai.ports.interfaces import StylePreferencesInput, WardrobeCategory
from services.ai_routing_specs import HIGH_STAKES_MODEL_ID
from services.app_config import AppConfigService, AppConfigSnapshot
from services.cost_budget_gate import CostBudgetGate
from services.engine_v2 import EngineV2
from services.engine_v2_portfolio import compute_outfit_fingerprint
from services.garment_registry_adapter import GarmentRegistryAdapter
from services.ist_window import ist_today
from services.occasion_normalizer import OccasionNormalizer
from services.outfit_portfolio_service import OutfitPortfolioService
from services.provider_quota import ProviderQuotaTracker
from services.routing_mix_monitor import RoutingMixMonitor
from services.styling_rules_engine import render_candidate_for_prompt
from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput
from services.suggestion_narration_cache import NarrationCacheOrchestrator

os.environ.setdefault("SUGGESTION_CACHE_SALT", "ss020-live-latency-verify-salt")


# ---------------------------------------------------------------------------
# Fakes for the non-AI-provider collaborators only (see module docstring).
# ---------------------------------------------------------------------------


class _FakeWardrobeRepo(IWardrobeRepository):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def upsert_uploaded_row(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def update_bg_removal_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        return "atelier"

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
        return None


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
        self.outcome_updates: list[dict[str, Any]] = []

    async def log_session(
        self, session: SuggestionSessionLog, impressions: Sequence[SuggestionImpressionLog]
    ) -> str:
        return "ss020-verify-session"

    async def log_outcome(self, outcome: Any) -> None:
        return None

    async def recent_impressions(self, *, user_id: str, since: Any, limit: int = 200) -> list[dict]:
        return []

    async def update_session_outcome(
        self, *, session_id: str, cost_incurred: bool, request_id: str | None, latency_ms: int | None
    ) -> None:
        self.outcome_updates.append(
            {
                "session_id": session_id,
                "cost_incurred": cost_incurred,
                "request_id": request_id,
                "latency_ms": latency_ms,
            }
        )


class _AlwaysMissNarrationCacheRepo(ISuggestionNarrationCacheRepository):
    """COLD cache, by construction -- `get()` always returns None."""

    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        return None

    async def put(self, **kwargs: Any) -> None:
        return None


class _FakeRateLimiter(IRateLimiter):
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        current = self.counters.get(key, 0) + amount
        self.counters[key] = current
        return RateLimitDecision(allowed=True, current=current, ceiling=ceiling, degraded=False)

    async def adjust(self, *, key: str, delta: int) -> None:
        self.counters[key] = self.counters.get(key, 0) + delta

    async def peek(self, *, key: str) -> int | None:
        return self.counters.get(key)


class _ClaudeOnlyRegistry:
    """`.get(provider, model)` returns the REAL `ClaudeStylingAdapter` for
    exactly the (claude, HIGH_STAKES_MODEL_ID) pair the routing table sends
    `occasion="wedding_guest"` to; None otherwise (no failover target
    registered on purpose -- this script proves the happy path, per
    `BL-100`)."""

    def __init__(self, adapter: ClaudeStylingAdapter) -> None:
        self._adapter = adapter

    def get(self, provider: str, model: str) -> ClaudeStylingAdapter | None:
        if provider == "claude" and model == HIGH_STAKES_MODEL_ID:
            return self._adapter
        return None


# ---------------------------------------------------------------------------
# Synthetic ~45-item wardrobe, wide category spread (western + ethnic +
# footwear + accessories -- ethnic wear is first-class per CLAUDE.md, not an
# edge case) so Engine v2's candidate search actually has a non-trivial pool
# to score, not a degenerate 1-item case.
# ---------------------------------------------------------------------------

_CATEGORIES: list[WardrobeCategory] = [
    "western_top",
    "western_bottom",
    "western_dress",
    "western_outerwear",
    "ethnic_kurta",
    "ethnic_saree",
    "ethnic_lehenga",
    "ethnic_anarkali",
    "ethnic_salwar_kameez",
    "ethnic_dupatta",
    "ethnic_sherwani",
    "indo_western",
    "footwear_formal",
    "footwear_casual",
    "footwear_ethnic",
    "accessory_bag",
    "accessory_jewellery",
]

_COLORS = ["#1E3A8A", "#8B0000", "#228B22", "#000000", "#FFD700", "#4B0082", "#DC143C"]


def _wardrobe_rows(n: int = 45) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        category = _CATEGORIES[i % len(_CATEGORIES)]
        color = _COLORS[i % len(_COLORS)]
        rows.append(
            {
                "id": f"item-{i}",
                "category": category,
                "color_primary": color,
                "color_secondary": None,
                "pattern": "solid",
                "fabric": "cotton",
                "occasion_tags": ["wedding_guest", "festival"],
                "season_tags": ["all"],
                "wear_count": i % 5,
                "last_worn_at": None,
            }
        )
    return rows


def _occasion_snapshot() -> OccasionRegistrySnapshot:
    return OccasionRegistrySnapshot(
        keys=("wedding_guest",),
        aliases={},
        labels={"wedding_guest": "Wedding Guest"},
        badge_colors={"wedding_guest": "wedding"},
        kinds={"wedding_guest": "ceremony"},
        formalities={"wedding_guest": 9},
        styling_rules={"wedding_guest": {}},
    )


def _empty_app_config() -> AppConfigService:
    from adapters.interfaces import IAppConfigRepository

    class _EmptyConfigRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict[str, Any]:
            return {}

    return AppConfigService(_EmptyConfigRepo())


def _empty_snapshot() -> AppConfigSnapshot:
    return AppConfigSnapshot(values={}, fetched_at=time.monotonic(), stale=False)


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[FAIL] ANTHROPIC_API_KEY is not set in this process's environment -- "
            "cannot make the real live call this script exists to make. "
            "Run with `set -a && source ../.env && set +a` first (from backend/)."
        )
        return 1

    log_repo = _FakeSuggestionLogRepo()
    wardrobe_repo = _FakeWardrobeRepo(_wardrobe_rows(45))
    occasion_normalizer = OccasionNormalizer(_FakeOccasionRepo(_occasion_snapshot()))
    app_config = _empty_app_config()
    engine = EngineV2(
        garment_registry=GarmentRegistryAdapter(_FakeGarmentRegistryRepo()),
        fabric_repo=_FakeFabricRepo(),
        wear_history_repo=_FakeWearHistoryRepo(),
        suggestion_log_repo=log_repo,
        app_config=app_config,
    )
    claude_adapter = ClaudeStylingAdapter(model=HIGH_STAKES_MODEL_ID)

    service = OutfitPortfolioService(
        wardrobe_repo=wardrobe_repo,
        occasion_normalizer=occasion_normalizer,
        engine=engine,
        app_config=app_config,
        routing_mix_monitor=RoutingMixMonitor(),
        cost_budget_gate=CostBudgetGate(_FakeRateLimiter(), app_config),
        provider_registry=_ClaudeOnlyRegistry(claude_adapter),
        provider_quota=ProviderQuotaTracker(),
        narration_cache=NarrationCacheOrchestrator(_AlwaysMissNarrationCacheRepo()),
        suggestion_log_repo=log_repo,
    )

    print(
        "Calling POST /outfit-suggestions/portfolio equivalent: "
        "45-item wardrobe, occasion=wedding_guest (routes to claude/"
        f"{HIGH_STAKES_MODEL_ID}), cold cache, expecting E2 tier..."
    )
    wall_start = time.perf_counter()
    result = await service.generate_portfolio_for_request(
        user_id="ss020-verify-user",
        jwt="ss020-verify-fake-jwt",
        occasion="wedding_guest",
        season=None,
        as_of=None,
        style_preferences_override=None,
        config_snapshot=_empty_snapshot(),
    )
    wall_elapsed_ms = (time.perf_counter() - wall_start) * 1000

    print()
    print(f"effort_tier        = {result['effort_tier']}")
    print(f"cache_hit           = {result['cache_hit']}")
    print(f"limited_options     = {result['limited_options']}")
    print(f"portfolio size      = {len(result['portfolio'])}")
    if result["portfolio"]:
        print(f"first rationale     = {result['portfolio'][0]['rationale'][:120]!r}")
        print(f"first rationale lang= {result['portfolio'][0]['rationale_language']}")
    print(f"session outcome logs= {log_repo.outcome_updates}")
    print()
    print(f"MEASURED WALL-CLOCK LATENCY (cold, E2, claude-sonnet-5): {wall_elapsed_ms:.0f} ms")

    ok = result["effort_tier"] == "E2" and result["cache_hit"] is False
    if not ok:
        print(
            "[WARN] did not land on the expected E2/cold-cache path -- "
            "latency number below may not be representative of the AC's "
            "'cold call' scenario."
        )
    print()
    print(f"End-to-end pipeline AC check (<4000ms happy-path, per BL-100): "
          f"{'PASS' if wall_elapsed_ms < 4000 else 'FAIL (see BL-067/BL-100 renegotiation precedent)'}")

    # ------------------------------------------------------------------
    # Supplementary direct-adapter measurement: the pipeline run above
    # goes through StylingRouter's own `attempt_timeout_seconds` (coded
    # default 6.0s, RouterPolicyConfig) -- if the real call is slower than
    # that, the router legitimately times it out and degrades (this IS a
    # true finding, not a bug in this script). To also capture the TRUE,
    # un-truncated Claude latency (not clipped by the router's own guard),
    # call `ClaudeStylingAdapter.narrate_candidates_with_metrics` directly
    # against the same candidate shapes, with its own generous 30s
    # per-adapter `timeout_seconds`.
    # ------------------------------------------------------------------
    print()
    print("Supplementary: direct ClaudeStylingAdapter call (bypasses StylingRouter's "
          "6s attempt_timeout, uses the adapter's own 30s timeout) to capture the "
          "TRUE, un-truncated API latency...")
    engine_result = await engine.generate_portfolio(
        [WardrobeItemInput.model_validate(r) for r in _wardrobe_rows(45)],
        OccasionStylingInput(key="wedding_guest", kind="ceremony", formality=9, styling_rules={}),
        jwt="ss020-verify-fake-jwt",
        user_id="ss020-verify-user",
        as_of=ist_today(),
        style_preferences=StylePreferencesInput(),
        search_pool_size=5000,
        mmr_lambda=0.75,
        max_exploration=1,
    )
    top = sorted(
        engine_result.portfolio,
        key=lambda pc: (-pc.candidate.total_score, tuple(pc.candidate.item_ids)),
    )[:6]
    rendered_candidates = []
    for pc in top:
        rendered = render_candidate_for_prompt(pc.candidate)
        rendered["outfit_fingerprint"] = compute_outfit_fingerprint(pc.candidate.item_ids)
        rendered_candidates.append(rendered)

    direct_start = time.perf_counter()
    try:
        narrated_result, metrics = await claude_adapter.narrate_candidates_with_metrics(
            rendered_candidates,
            occasion="wedding_guest",
            preferences=StylePreferencesInput(),
            max_suggestions=6,
        )
        direct_elapsed_ms = (time.perf_counter() - direct_start) * 1000
        print("direct call source   = claude (succeeded)")
        print(f"direct call tokens   = in={metrics.tokens_in} out={metrics.tokens_out}")
        print(f"direct call narrations = {len(narrated_result.narrations)}")
        print(f"MEASURED TRUE ADAPTER LATENCY (claude-sonnet-5, un-truncated): {direct_elapsed_ms:.0f} ms")
    except Exception as exc:  # noqa: BLE001 -- this is a diagnostic script
        direct_elapsed_ms = (time.perf_counter() - direct_start) * 1000
        print(f"[FAIL] direct claude call raised after {direct_elapsed_ms:.0f} ms: {exc!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
