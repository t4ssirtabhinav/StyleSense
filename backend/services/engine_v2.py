"""SS-038 -- Engine v2: the orchestrator for the four-stage wide-search /
attribute-scoring / MMR-portfolio pipeline that replaces
``styling_rules_engine.generate_candidates``/``score_candidate``.

``EngineV2.generate_portfolio`` is the ONLY async/I/O boundary in the whole
pipeline -- every stage module it calls (``engine_v2_eligibility``,
``engine_v2_candidate_search``, ``engine_v2_attribute_scoring``,
``engine_v2_portfolio``) is pure. The two real I/O calls are: (1)
``GarmentRegistryAdapter.refresh()``/``IFabricRegistryRepository.fetch_all()``
(reference-data reads), and (2) ``engine_v2_novelty.fetch_novelty_inputs``
(wear history + impression history, both contractually never-raising).

**Fixes, by stage, vs. SS-027/037's ``styling_rules_engine.py`` (matching
that file's own "successor docstring" discipline):**

- Stage②: footwear/accessory/outerwear were a function of the item alone
  (same shoe on every candidate) -- fixed via top-N-per-remaining-slot
  expansion, not single-best. Colour was absent from the old per-slot
  capping formula -- fixed by folding ``pairwise_colour_harmony`` into the
  base-ranking key itself.
- Stage③: ``_colour_harmony_score``'s star-topology -- fixed by
  ``pairwise_colour_harmony`` (resolves ``BL-128``'s star-topology half).
- Stage①: the near-white threshold was a hardcoded Python literal -- now an
  ``app_config`` row with a per-occasion override (resolves ``BL-111``).
- ``engine_version`` was never bumped on any suggestion-log row -- this
  module writes ``"engine-v2"`` (resolves ``BL-114``).
- ``wear_recency()``/``IWearHistoryRepository`` had zero callers --
  ``engine_v2_novelty.fetch_novelty_inputs`` is the first real one (resolves
  ``BL-119``).
- ``suggestion_impressions`` had no real writer, only test fixtures -- this
  module is the first.

**Explicitly still open, named so a future reader does not re-derive them
as new findings:**

- ``_hue_distance_score``'s flat ``0.75`` fallback for unparsable/named
  colours (``BL-128``'s fallback half) -- needs ``BL-064``/``BL-079``'s
  hex-to-colour-family binning first, deliberately not built here.
- ``patterns`` has no attribute columns (``BL-126``).
- Garment-set item-level consumption (``BL-116``).
- ``wardrobe_item_wears.outfit_id``'s write half (``BL-120``, SS-020/SS-023's job).
- Mark Worn's ``occasion_key=NULL`` product question (``BL-121``, SS-020/SS-023's job).
- Which occasion kinds set ``outerwear_required`` -- content authoring
  (``BL-129``'s authoring half, folds into ``BL-097``).
- Coverage x modesty scoring -- no live data (``garment_types.coverage`` is
  empty for all seeded rows, ``users.body_type``/modesty preference
  unpopulated) -- new ``BL-133``.
- **``volume_balance``/``register_coherence``/``BL-129``'s register-
  coherence ranking fix are architecturally correct and unit-tested but
  100% LIVE-INERT today** -- no live ``wardrobe_items.category`` value
  currently resolves through ``garment_types`` (SS-034 seeded new-vocabulary
  keys under different names than the 21-value enum still in live use), so
  every real wardrobe hits the graceful-neutral-degrade path for these three
  terms until Wave 2's taxonomy migration (new ``BL-132``). This is
  expected and documented, NOT a bug to work around -- do not add
  workarounds to make it "appear" active against current live data.

**Cost-accounting posture (an inference, not literally specified by the
design doc's own step-11 text):** ``generate_portfolio`` never calls an AI
provider itself -- it is a deterministic Python pipeline, so every session
it logs is written with ``cost_incurred=False, zero_cost_reason="rules_only"``
(an existing, already-seeded ``suggestion_sessions.zero_cost_reason`` CHECK
value from SS-033, chosen here as the closest fit rather than inventing a
new one).

**Constructing a real ``EngineV2`` (guidance for SS-020's Architect pass,
per this ticket's own "Open questions" #5 -- this ticket ships no router, so
nothing calls the constructor in production yet):** see
``build_default_engine_v2()`` below.
"""

from __future__ import annotations

import logging
from datetime import date

from adapters.fabric_registry_repository import SupabaseFabricRegistryRepository
from adapters.interfaces import (
    FabricAttributes,
    IFabricRegistryRepository,
    ISuggestionLogRepository,
    IWearHistoryRepository,
    SuggestionImpressionLog,
    SuggestionSessionLog,
)
from adapters.suggestion_log_repository import SupabaseSuggestionLogRepository
from adapters.wear_history_repository import SupabaseWearHistoryRepository
from ai.ports.interfaces import SeasonTag, StylePreferencesInput
from services import (
    engine_v2_attribute_scoring,
    engine_v2_candidate_search,
    engine_v2_eligibility,
    engine_v2_novelty,
    engine_v2_portfolio,
)
from services.app_config import AppConfigService, app_config_service
from services.engine_v2_portfolio import compute_outfit_fingerprint
from services.engine_v2_types import EngineV2Result, PortfolioCandidate
from services.garment_registry_adapter import GarmentRegistryAdapter, garment_registry_adapter
from services.styling_rules_defaults import (
    DEFAULT_MAX_EXPLORATION,
    DEFAULT_MMR_LAMBDA,
    DEFAULT_PORTFOLIO_SIZE_RANGE,
    DEFAULT_SCORE_FLOOR,
)
from services.styling_rules_types import GapReport, OccasionStylingInput, WardrobeItemInput

logger = logging.getLogger(__name__)

ENGINE_VERSION = "engine-v2"

__all__ = ["EngineV2", "build_default_engine_v2", "ENGINE_VERSION"]


class EngineV2:
    """Constructor-injected with the registry adapter/repositories this
    pipeline needs. No I/O happens at construction time."""

    def __init__(
        self,
        *,
        garment_registry: GarmentRegistryAdapter,
        fabric_repo: IFabricRegistryRepository,
        wear_history_repo: IWearHistoryRepository,
        suggestion_log_repo: ISuggestionLogRepository,
        app_config: AppConfigService,
    ) -> None:
        self._garment_registry = garment_registry
        self._fabric_repo = fabric_repo
        self._wear_history_repo = wear_history_repo
        self._suggestion_log_repo = suggestion_log_repo
        self._app_config = app_config

    async def generate_portfolio(
        self,
        wardrobe: list[WardrobeItemInput],
        occasion: OccasionStylingInput,
        *,
        jwt: str,
        user_id: str,
        as_of: date,
        season: SeasonTag | None = None,
        style_preferences: StylePreferencesInput | None = None,
        portfolio_size_range: tuple[int, int] = DEFAULT_PORTFOLIO_SIZE_RANGE,
        max_exploration: int = DEFAULT_MAX_EXPLORATION,
    ) -> EngineV2Result:
        """The only async/I/O boundary in the whole pipeline -- see module
        docstring for the exact sequence."""
        await self._garment_registry.refresh()

        try:
            fabric_attrs: dict[str, FabricAttributes] = await self._fabric_repo.fetch_all()
        except Exception as exc:  # noqa: BLE001 -- a fabric-read failure must never block a suggestion
            logger.warning("engine_v2_fabric_registry_fetch_failed", extra={"error": str(exc)})
            fabric_attrs = {}

        rules = engine_v2_eligibility.resolve_styling_rules(occasion)
        app_config_snapshot = await self._app_config.snapshot()
        near_white = engine_v2_eligibility.resolve_near_white_thresholds(
            app_config_snapshot, rules
        )
        eligibility = engine_v2_eligibility.filter_eligible(
            wardrobe, occasion, rules, near_white_thresholds=near_white
        )

        novelty_inputs = await engine_v2_novelty.fetch_novelty_inputs(
            self._wear_history_repo,
            self._suggestion_log_repo,
            jwt=jwt,
            user_id=user_id,
            occasion_key=occasion.key,
            as_of=as_of,
        )

        search_result = engine_v2_candidate_search.search_candidates(
            eligibility.eligible_items,
            occasion=occasion,
            garment_lookup=self._garment_registry.get_garment_attributes,
            rules=rules,
            as_of=as_of,
            season=season,
            style_preferences=style_preferences,
        )

        scored = [
            engine_v2_attribute_scoring.score_assembled_candidate(
                candidate,
                occasion,
                rules,
                garment_lookup=self._garment_registry.get_garment_attributes,
                fabric_attrs=fabric_attrs,
                novelty_inputs=novelty_inputs,
                as_of=as_of,
                season=season,
                style_preferences=style_preferences,
            )
            for candidate in search_result.candidates
        ]

        gap_report = GapReport(
            excluded_missing_color_or_category=eligibility.excluded_missing_color_or_category,
            missing_slots=search_result.missing_slots,
        )
        portfolio_result = engine_v2_portfolio.select_portfolio(
            scored,
            score_floor=DEFAULT_SCORE_FLOOR,
            lambda_=DEFAULT_MMR_LAMBDA,
            gap_report=gap_report,
            portfolio_size_range=portfolio_size_range,
            max_exploration=max_exploration,
        )

        session_id = await self._log_session(
            user_id=user_id,
            occasion=occasion,
            candidate_count=len(scored),
            portfolio=portfolio_result.portfolio,
        )

        return EngineV2Result(
            portfolio=portfolio_result.portfolio,
            limited_options=portfolio_result.limited_options,
            gap_report=portfolio_result.gap_report,
            session_id=session_id,
            engine_version=ENGINE_VERSION,
        )

    async def _log_session(
        self,
        *,
        user_id: str,
        occasion: OccasionStylingInput,
        candidate_count: int,
        portfolio: list[PortfolioCandidate],
    ) -> str | None:
        """Best-effort log -- wrapped in its own try/except even though both
        underlying port methods already contractually never raise (design
        §5.4/§11's "belt and suspenders" posture, mirrors
        ``SuggestionLogService.log_suggestion``'s own defensive wrapping).
        ``session_id`` may be ``None``; this never blocks the caller's
        return."""
        try:
            session = SuggestionSessionLog(
                user_id=user_id,
                occasion=occasion.key,
                engine_version=ENGINE_VERSION,
                candidate_count=candidate_count,
                cost_incurred=False,
                zero_cost_reason="rules_only",
            )
            impressions = [
                SuggestionImpressionLog(
                    rank=rank,
                    item_ids=list(pc.candidate.item_ids),
                    outfit_fingerprint=compute_outfit_fingerprint(pc.candidate.item_ids),
                    total_score=pc.candidate.total_score,
                    rule_scores=[rs.model_dump() for rs in pc.candidate.rule_scores],
                    gap_flags=list(pc.candidate.gap_flags),
                    is_exploration=pc.is_exploration,
                    strategy=pc.strategy,
                )
                for rank, pc in enumerate(portfolio, start=1)
            ]
            return await self._suggestion_log_repo.log_session(session, impressions)
        except Exception as exc:  # noqa: BLE001 -- logging must never fail the suggestion request
            logger.error("engine_v2_session_log_failed", extra={"user_id": user_id, "error": str(exc)})
            return None


def build_default_engine_v2() -> EngineV2:
    """Guidance for SS-020's Architect pass (this ticket ships no router, so
    nothing calls the constructor in production yet) -- the minimal, real-
    repository wiring. Reuses the module-scope ``garment_registry_adapter``/
    ``app_config_service`` singletons (both constructed with ZERO I/O, safe
    to import anywhere) rather than constructing fresh instances of those
    two -- everything else is a plain per-call repository, same posture as
    ``fabric_registry_repository.py``'s own module docstring explains for
    why it needs no cross-request cache."""
    return EngineV2(
        garment_registry=garment_registry_adapter,
        fabric_repo=SupabaseFabricRegistryRepository(),
        wear_history_repo=SupabaseWearHistoryRepository(),
        suggestion_log_repo=SupabaseSuggestionLogRepository(),
        app_config=app_config_service,
    )
