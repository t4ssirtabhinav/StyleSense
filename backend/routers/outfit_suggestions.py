"""Stub endpoint proving the IStylingProvider -> OutfitSuggestionService ->
router wiring end-to-end (SS-006). Canned output only -- no real
personalization, no real auth, no real result-delivery mechanism yet (see
docs/tickets/SS-006-design.md's "Open questions").

(SS-028) ``get_styling_provider()`` now builds a ``StylingRouter`` per
request -- the composition root where the port swap the ticket's own
framing calls out actually happens ("the first real proof the ports
architecture pays for itself"). Every ``Depends()`` helper below ultimately
depends on ``get_app_config_snapshot`` (``dependencies/app_config.py``),
which FastAPI caches per request by default -- so exactly ONE
``AppConfigService.snapshot()`` call backs every read in a single request,
satisfying design §4.4/N2 by construction, not by convention.

(SS-020) ``POST /outfit-suggestions/portfolio`` is a SEPARATE, real
endpoint added by this ticket -- ``OutfitPortfolioService`` orchestrates
occasion resolution -> wardrobe fetch -> Engine v2 -> narration cache ->
LLM narration -> response assembly, awaited SYNCHRONOUSLY inside the
request handler (no ``BackgroundTasks`` -- see
``docs/worklog/SS-020.md``'s Open Question #1 sign-off). Auth for this
route is the REAL, signature-verified ``dependencies.auth.get_current_user_id``
(closes ``BL-052`` for this route only) -- the pre-existing ``/generate``
route below and its ``get_current_user_id_stub`` auth are UNTOUCHED by this
ticket (Open Question #6): no caller depends on migrating them, and doing
so would expand this ticket's diff into an unrelated route.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from adapters.interfaces import (
    IOutfitRepository,
    ISuggestionLogRepository,
    ISuggestionRailsRepository,
    IWardrobeRepository,
)
from adapters.occasion_repository import SupabaseOccasionRepository
from adapters.open_meteo_weather_adapter import OpenMeteoWeatherAdapter
from adapters.outfit_repository import SupabaseOutfitRepository
from adapters.suggestion_log_repository import SupabaseSuggestionLogRepository
from adapters.suggestion_narration_cache_repository import (
    SupabaseSuggestionNarrationCacheRepository,
)
from adapters.suggestion_rails_repository import SupabaseSuggestionRailsRepository
from adapters.upstash_rate_limiter import UpstashRateLimiter
from adapters.wardrobe_repository import SupabaseWardrobeRepository
from ai.adapters.styling_provider_registry import StylingProviderRegistry
from ai.ports.interfaces import IStylingProvider
from dependencies.app_config import get_app_config_snapshot
from dependencies.auth import get_current_user_id
from services.ai_routing_specs import (
    AI_PROVIDER_QUOTA_SPEC,
    AI_ROUTER_POLICY_SPEC,
    AI_STYLING_ROUTING_TABLE_SPEC,
)
from services.app_config import AppConfigSnapshot, app_config_service
from services.cost_budget_gate import CostBudgetGate
from services.engine_v2 import build_default_engine_v2
from services.garment_registry_adapter import garment_registry_adapter
from services.occasion_normalizer import OccasionNormalizer
from services.outfit_outcome_service import OutcomeNotFoundError, OutfitOutcomeService
from services.outfit_portfolio_service import OutfitPortfolioService
from services.outfit_suggestion_service import OutfitSuggestionService
from services.provider_quota import ProviderQuotaTracker
from services.rail_precompute_service import RailPrecomputeService
from services.rail_staleness import maybe_trigger_rail_recompute
from services.routing_mix_monitor import RoutingMixMonitor
from services.styling_router import RoutingContext, StylingRouter
from services.suggestion_narration_cache import NarrationCacheOrchestrator
from services.weather_cache import WeatherCache
from services.weather_service import WeatherService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outfit-suggestions", tags=["outfit-suggestions"])

# Process-wide singletons -- same reasoning as routers/wardrobe.py's
# _gemini_rate_limiter/_occasion_normalizer: each holds real in-process
# state (a sliding-window quota reservation, a rolling routing-mix sample,
# a per-(provider,model) adapter cache) that only means anything if it
# survives across requests. Built with ZERO I/O at import (mirrors that
# same file's pattern exactly); still swappable via dependency_overrides
# for tests.
_provider_quota_tracker = ProviderQuotaTracker()
_routing_mix_monitor = RoutingMixMonitor()
_styling_provider_registry = StylingProviderRegistry()

# (SS-020) Same "zero-I/O at construction, real in-process state that only
# means anything across requests" reasoning as the three singletons above --
# _occasion_normalizer's 60s TTL registry cache and _cost_rate_limiter's
# Upstash-backed (stateless per call, but symmetrically module-level for one
# fewer allocation per request) client. Both swappable via
# dependency_overrides for tests.
_occasion_normalizer = OccasionNormalizer(SupabaseOccasionRepository())
_cost_rate_limiter = UpstashRateLimiter()
_wardrobe_repository = SupabaseWardrobeRepository()
_suggestion_log_repository = SupabaseSuggestionLogRepository()
_outfit_repository = SupabaseOutfitRepository()
_narration_cache_orchestrator = NarrationCacheOrchestrator(
    SupabaseSuggestionNarrationCacheRepository()
)
_engine_v2 = build_default_engine_v2()
# (SS-022) Same "zero-I/O at construction" reasoning -- OpenMeteoWeatherAdapter
# and WeatherCache both hold no state that needs per-request construction.
_weather_service = WeatherService(
    wardrobe_repo=_wardrobe_repository,
    provider=OpenMeteoWeatherAdapter(),
    cache=WeatherCache(),
    app_config=app_config_service,
)

# (SS-048) Reuses this router's own _wardrobe_repository/_outfit_repository/
# _occasion_normalizer/_engine_v2 singletons above -- no shared mutable state
# with routers/wardrobe.py or routers/suggestion_rails.py's own (separate)
# instances, except garment_registry_adapter, deliberately shared process-wide
# (see services/engine_v2.py's own module docstring).
_rails_repository = SupabaseSuggestionRailsRepository()
_rail_precompute_service = RailPrecomputeService(
    engine=_engine_v2,
    wardrobe_repo=_wardrobe_repository,
    outfit_repo=_outfit_repository,
    garment_registry=garment_registry_adapter,
    rails_repo=_rails_repository,
    occasion_normalizer=_occasion_normalizer,
)


def get_current_user_id_stub(authorization: str | None = Header(default=None)) -> str:
    """NON-PRODUCTION STUB. Reads the JWT payload's `sub` claim WITHOUT
    verifying the token's signature. This is UNSAFE for real traffic --
    acceptable only because nothing behind this router is real (mock
    adapter, no writes, no sensitive reads, no deployed caller yet).

    Before any real traffic reaches this or any future backend endpoint, a
    proper Supabase JWT-verification dependency must replace this. Logged
    as BL-033 (Active, tag `auth`) -- do not treat this as real auth.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Malformed or non-JWT-shaped token") from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")

    return str(sub)


def get_styling_provider_registry() -> StylingProviderRegistry:
    return _styling_provider_registry


def get_provider_quota_tracker(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
) -> ProviderQuotaTracker:
    quota_config = app_config_service.read(snapshot, AI_PROVIDER_QUOTA_SPEC)
    ceilings = {provider: (entry.rpm, entry.tpm) for provider, entry in quota_config.root.items()}
    _provider_quota_tracker.set_ceilings(ceilings)
    return _provider_quota_tracker


def get_routing_mix_monitor(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
) -> RoutingMixMonitor:
    policy = app_config_service.read(snapshot, AI_ROUTER_POLICY_SPEC)
    _routing_mix_monitor.configure(
        alert_min_sample=policy.alert_min_sample,
        expensive_share_alert_threshold=policy.expensive_share_alert_threshold,
        alert_cooldown_seconds=policy.alert_cooldown_seconds,
        provider_outage_alert_seconds=policy.provider_outage_alert_seconds,
    )
    return _routing_mix_monitor


def get_routing_context(user_id: str = Depends(get_current_user_id_stub)) -> RoutingContext:
    """(SS-028) Every field beyond ``user_id`` stays at its default (cheap/
    everyday route) until a real caller supplies tier/occasion/first-
    suggestion signals -- SS-020's job, not this ticket's (constraint §2.4:
    unknown context routes cheap, never "to be safe" expensive)."""
    return RoutingContext(user_id=user_id)


def get_styling_provider(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
    registry: StylingProviderRegistry = Depends(get_styling_provider_registry),
    quota: ProviderQuotaTracker = Depends(get_provider_quota_tracker),
    monitor: RoutingMixMonitor = Depends(get_routing_mix_monitor),
    context: RoutingContext = Depends(get_routing_context),
) -> IStylingProvider:
    """The binding from port to concrete adapter lives here, and only here --
    the route handler below never imports StylingRouter/MockStylingAdapter
    directly. Override this dependency (via app.dependency_overrides) to
    swap in a different IStylingProvider without touching this router file
    -- the exact seam SS-006 documented, still intact after SS-028.
    """
    routing_table = app_config_service.read(snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
    policy = app_config_service.read(snapshot, AI_ROUTER_POLICY_SPEC)
    return StylingRouter(
        registry=registry,
        routing_table=routing_table,
        policy=policy,
        quota=quota,
        monitor=monitor,
        context=context,
        snapshot_stale=snapshot.stale,
    )


def get_outfit_suggestion_service(
    provider: IStylingProvider = Depends(get_styling_provider),
) -> OutfitSuggestionService:
    return OutfitSuggestionService(provider)


class GenerateSuggestionsRequest(BaseModel):
    """Raw, unvalidated style_preferences payload -- mirrors the nullable
    JSONB shape of users.style_preferences. Validated/normalized inside
    OutfitSuggestionService, not here (single source of truth for the
    null/partial/malformed degrade path)."""

    style_preferences: dict[str, Any] | None = None


@router.post("/generate", status_code=202)
async def generate_outfit_suggestions(
    background_tasks: BackgroundTasks,
    request: GenerateSuggestionsRequest | None = None,
    user_id: str = Depends(get_current_user_id_stub),
    service: OutfitSuggestionService = Depends(get_outfit_suggestion_service),
) -> dict[str, Any]:
    try:
        raw_preferences = request.style_preferences if request else None
        background_tasks.add_task(service.generate_suggestions, user_id, raw_preferences)
        return {"status": "queued", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("outfit_suggestions_generate_failed", extra={"user_id": user_id})
        raise HTTPException(
            status_code=500, detail="Failed to queue outfit suggestion generation"
        ) from exc


# ---------------------------------------------------------------------------
# SS-020 -- POST /outfit-suggestions/portfolio (real endpoint, real auth).
# ---------------------------------------------------------------------------


def get_wardrobe_repository() -> IWardrobeRepository:
    return _wardrobe_repository


def get_suggestion_log_repository() -> ISuggestionLogRepository:
    return _suggestion_log_repository


def get_cost_budget_gate() -> CostBudgetGate:
    return CostBudgetGate(_cost_rate_limiter, app_config_service)


def get_occasion_normalizer() -> OccasionNormalizer:
    return _occasion_normalizer


def get_narration_cache() -> NarrationCacheOrchestrator:
    return _narration_cache_orchestrator


def get_weather_service() -> WeatherService:
    return _weather_service


def get_outfit_portfolio_service(
    wardrobe_repo: IWardrobeRepository = Depends(get_wardrobe_repository),
    occasion_normalizer: OccasionNormalizer = Depends(get_occasion_normalizer),
    monitor: RoutingMixMonitor = Depends(get_routing_mix_monitor),
    cost_budget_gate: CostBudgetGate = Depends(get_cost_budget_gate),
    registry: StylingProviderRegistry = Depends(get_styling_provider_registry),
    quota: ProviderQuotaTracker = Depends(get_provider_quota_tracker),
    narration_cache: NarrationCacheOrchestrator = Depends(get_narration_cache),
    suggestion_log_repo: ISuggestionLogRepository = Depends(get_suggestion_log_repository),
    weather_service: WeatherService = Depends(get_weather_service),
) -> OutfitPortfolioService:
    """The binding from "everything /portfolio needs" to a real
    ``OutfitPortfolioService`` lives here, and only here -- the route
    handler below never imports a concrete adapter directly. Override via
    ``app.dependency_overrides`` to swap in fakes for tests."""
    return OutfitPortfolioService(
        wardrobe_repo=wardrobe_repo,
        occasion_normalizer=occasion_normalizer,
        engine=_engine_v2,
        app_config=app_config_service,
        routing_mix_monitor=monitor,
        cost_budget_gate=cost_budget_gate,
        provider_registry=registry,
        provider_quota=quota,
        narration_cache=narration_cache,
        suggestion_log_repo=suggestion_log_repo,
        weather_service=weather_service,
    )


class GeneratePortfolioRequest(BaseModel):
    occasion: str  # raw text or registry key; normalised server-side
    season: Literal["summer", "winter", "monsoon", "all"] | None = None
    as_of: date | None = None  # default: today, IST (services/ist_window.py)
    style_preferences_override: dict[str, Any] | None = (
        None  # None => server fetches users.style_preferences
    )
    # (SS-023) The regenerate mechanism (design §4). Fingerprints the caller
    # has already been shown/dismissed in this session. Untrusted but
    # harmless: the only thing a forged value can do is shrink the caller's
    # own result set. Capped server-side; over-cap is TRUNCATED
    # (oldest-first by client order), never a 422.
    exclude_fingerprints: list[str] = Field(default_factory=list, max_length=60)


class PortfolioItemResponse(BaseModel):
    item_ids: list[str]
    category_labels: dict[str, str]
    total_score: float
    rationale: str
    rationale_language: Literal["en", "hi"]
    is_exploration: bool
    gap_flags: list[str]
    # (SS-023) 1-based, EXACTLY the rank written to
    # suggestion_impressions.rank by EngineV2._log_session -- the join key
    # /outfit-suggestions/outcome resolves on.
    rank: int
    outfit_fingerprint: str  # 64-char lowercase hex


class WeatherResponse(BaseModel):
    """(SS-022) Mirrors ``services.weather_rules.WeatherContext`` --
    ``Literal``-constrained ``condition`` so an unmappable WMO code (already
    degraded to ``"cloudy"`` in ``weather_rules.condition_for_wmo_code``)
    can never fail validation at this boundary."""

    city: str
    temp_c: float
    condition: Literal[
        "clear",
        "partly_cloudy",
        "cloudy",
        "fog",
        "drizzle",
        "rain",
        "heavy_rain",
        "thunderstorm",
        "snow",
    ]
    humidity: int
    is_heavy_rain: bool


class GeneratePortfolioResponse(BaseModel):
    portfolio: list[PortfolioItemResponse]
    limited_options: bool
    gap_report: dict[str, Any]
    engine_version: str
    effort_tier: str
    cache_hit: bool
    generated_at: str
    # (SS-023) None when session logging failed -- the client can still
    # render suggestions, but cannot record an outcome for that batch.
    session_id: str | None
    occasion_key: str  # RESOLVED canonical key (post-alias)
    # (SS-022) None when the user has no usable city or Open-Meteo was
    # unreachable -- never blocks the response.
    weather: WeatherResponse | None = None


@router.post("/portfolio", status_code=200, response_model=GeneratePortfolioResponse)
async def generate_outfit_portfolio(
    request: GeneratePortfolioRequest,
    user_id: str = Depends(get_current_user_id),
    authorization: str | None = Header(default=None),
    config_snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
    service: OutfitPortfolioService = Depends(get_outfit_portfolio_service),
) -> GeneratePortfolioResponse:
    """Awaited SYNCHRONOUSLY -- no ``BackgroundTasks`` (Open Question #1's
    signed-off deviation from CLAUDE.md's literal "never call AI APIs
    synchronously" wording; every I/O call inside the service is
    ``await``ed, never blocking the event loop with sync I/O). Never a
    hard error for anything narration-related -- unknown occasion, empty
    wardrobe, budget denial, provider failure, or a malformed LLM response
    all degrade to a still-``200`` response with rule-based rationale text."""
    jwt_token = _extract_bearer_token(authorization)
    try:
        result = await service.generate_portfolio_for_request(
            user_id=user_id,
            jwt=jwt_token,
            occasion=request.occasion,
            season=request.season,
            as_of=request.as_of,
            style_preferences_override=request.style_preferences_override,
            config_snapshot=config_snapshot,
            exclude_fingerprints=request.exclude_fingerprints,
        )
        return GeneratePortfolioResponse.model_validate(result)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("outfit_suggestions_portfolio_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to generate outfit portfolio") from exc


def _extract_bearer_token(authorization: str | None) -> str:
    """``get_current_user_id`` already validated the header shape/signature
    -- this just re-extracts the raw token string for RLS-scoped repository
    calls (mirrors ``routers/wardrobe.py``'s own ``_extract_bearer_token``)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


# ---------------------------------------------------------------------------
# SS-023 -- POST /outfit-suggestions/outcome (real endpoint, real auth).
# ---------------------------------------------------------------------------


def get_outfit_repository() -> IOutfitRepository:
    return _outfit_repository


def get_rails_repository() -> ISuggestionRailsRepository:
    """(SS-048) Backs the debounce staleness check /outcome runs (for
    'saved'/'worn') before returning its response."""
    return _rails_repository


def get_rail_precompute_service() -> RailPrecomputeService:
    return _rail_precompute_service


def get_outfit_outcome_service(
    suggestion_log_repo: ISuggestionLogRepository = Depends(get_suggestion_log_repository),
    outfit_repo: IOutfitRepository = Depends(get_outfit_repository),
    wardrobe_repo: IWardrobeRepository = Depends(get_wardrobe_repository),
) -> OutfitOutcomeService:
    """The binding from "everything /outcome needs" to a real
    ``OutfitOutcomeService`` lives here, and only here -- the route handler
    below never imports a concrete adapter directly. Override via
    ``app.dependency_overrides`` to swap in fakes for tests."""
    return OutfitOutcomeService(
        suggestion_log_repo=suggestion_log_repo,
        outfit_repo=outfit_repo,
        wardrobe_repo=wardrobe_repo,
    )


class RecordOutcomeRequest(BaseModel):
    session_id: str  # UUID string, from the portfolio response
    rank: int = Field(ge=1)  # which card in that session
    outcome_type: Literal["saved", "dismissed", "worn", "shared"]
    # ISO-8601; clamped server-side by the existing _clamp_client_occurred_at.
    client_occurred_at: str | None = None
    name: str | None = Field(default=None, max_length=80)  # optional user-given outfit name


class RecordOutcomeResponse(BaseModel):
    outfit_id: str | None  # non-None for 'saved'/'worn'/'shared'; None for 'dismissed'
    outcome_recorded: bool  # False = outcome logging degraded (outfits save is unaffected)
    already_saved: bool  # True when the idempotent path hit an existing outfit


@router.post("/outcome", status_code=200, response_model=RecordOutcomeResponse)
async def record_outfit_outcome(
    request: RecordOutcomeRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    authorization: str | None = Header(default=None),
    service: OutfitOutcomeService = Depends(get_outfit_outcome_service),
    config_snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
    rails_repo: ISuggestionRailsRepository = Depends(get_rails_repository),
    rail_precompute_service: RailPrecomputeService = Depends(get_rail_precompute_service),
) -> RecordOutcomeResponse:
    """``'shuffled_away'`` is in the DB's CHECK enum but is deliberately not
    exposed here -- this ticket has no shuffle gesture (design §1). Never a
    500 for a degraded log write -- only ``OutcomeNotFoundError`` (the
    cross-tenant/not-found case, design §3, the single highest-risk line in
    this ticket) maps to a 4xx; everything else that can go wrong inside
    the service degrades to ``outcome_recorded=False``, not an exception."""
    jwt_token = _extract_bearer_token(authorization)
    try:
        result = await service.record_outcome(
            user_id=user_id,
            jwt=jwt_token,
            session_id=request.session_id,
            rank=request.rank,
            outcome_type=request.outcome_type,
            client_occurred_at=request.client_occurred_at,
            name=request.name,
        )
        # (SS-048) Only 'saved'/'worn' are the writes never_tried_pairs/
        # not_yet_worn depend on (design doc's Debounce trigger wiring) --
        # 'dismissed'/'shared' don't change outfits.item_ids or wear_count,
        # so they don't warrant a recompute. Awaited directly, own
        # try/except (services/rail_staleness.py) -- never fails this
        # response.
        if request.outcome_type in ("saved", "worn"):
            await maybe_trigger_rail_recompute(
                jwt=jwt_token,
                user_id=user_id,
                background_tasks=background_tasks,
                rails_repo=rails_repo,
                rail_precompute_service=rail_precompute_service,
                config_snapshot=config_snapshot,
                app_config=app_config_service,
            )
        return RecordOutcomeResponse.model_validate(result)
    except OutcomeNotFoundError:
        # Deliberately 404, never 403 -- a 403 would confirm the session
        # exists, an enumeration oracle over another user's session ids
        # (design §3).
        raise HTTPException(status_code=404, detail="Suggestion not found") from None
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("outfit_suggestions_outcome_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to record outfit outcome") from exc
