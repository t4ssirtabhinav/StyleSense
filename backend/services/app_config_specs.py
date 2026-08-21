"""Demo-only ``ConfigSpec``s for SS-026's seeded keys (design §3.6), plus
SS-038's first real consumer spec.

Proves the ``app_config``/``AppConfigService`` substrate against real
acceptance criteria; wires NO real consumer. A future domain ticket may add
its own specs file near its own service rather than growing this one
indefinitely (flagged, not decided, in the design doc's §10).

``GEMINI_QUOTA_CEILING_SPEC``'s coded default (``rpm=15``) matches
``backend/services/gemini_rate_limiter.py``'s CURRENT hardcoded default
exactly -- if this key is ever read and the row is missing/malformed,
behaviour is IDENTICAL to today's, never a silent regression. Retires
``BL-076`` in spirit only: the mechanism exists, the constant does not move
in this ticket (that is SS-028's job).

``NEAR_WHITE_THRESHOLD_SPEC`` (SS-038, resolves ``BL-111``) moves the HSV
near-white/cream/ivory exclusion thresholds from a Python literal
(``styling_rules_defaults.NEAR_WHITE_VALUE_THRESHOLD``/
``NEAR_WHITE_SATURATION_THRESHOLD``) into an ``app_config`` row, coded
default IDENTICAL to those constants' current values -- a missing/malformed
row degrades to exactly today's behaviour, same SS-026 pattern as
``GEMINI_QUOTA_CEILING_SPEC``. ``engine_v2_eligibility.resolve_near_white_thresholds``
is the real consumer; see ``supabase/migrations/017_seed_engine_v2_near_white_config.sql``
for the seeded row and ``styling_rules_types.StylingRulesOverride``'s
``near_white_value_threshold``/``near_white_saturation_threshold`` fields for
the per-occasion override path.

``ENGINE_V2_EFFORT_TIER_SPEC`` (SS-039) wires the proposal's §6 tuning-dial
table's E0/E1/E2 rows into one ``app_config`` row. UNLIKE
``NEAR_WHITE_THRESHOLD_SPEC``'s "identical to today" posture, its coded
default is NOT a transcription of any pre-existing constant -- it is the
raw ticket's own literal E0-E2 table values, separately hardcoded here so a
missing/malformed row still degrades to that documented floor (AC #2), not
to ``styling_rules_defaults``'s pre-dial ``DEFAULT_MMR_LAMBDA``/
``DEFAULT_MAX_EXPLORATION`` constants. ``services/engine_v2_effort_dial.py``
is the real consumer (tier RESOLUTION only -- no live caller wires a
resolved tier into ``engine_v2_candidate_search``/``engine_v2_portfolio``
yet; that is SS-020's job). See
``supabase/migrations/018_seed_engine_v2_effort_dial_config.sql`` for the
seeded row.
"""

from __future__ import annotations

from pydantic import BaseModel

from services.app_config import ConfigSpec


class GeminiQuotaCeilingConfig(BaseModel):
    rpm: int = 15


GEMINI_QUOTA_CEILING_SPEC: ConfigSpec[GeminiQuotaCeilingConfig] = ConfigSpec(
    key="gemini_quota_ceiling_rpm",
    model=GeminiQuotaCeilingConfig,
    default=GeminiQuotaCeilingConfig(),
)


class NearWhiteThresholdConfig(BaseModel):
    """Coded defaults transcribed verbatim from
    ``styling_rules_defaults.NEAR_WHITE_VALUE_THRESHOLD``/
    ``NEAR_WHITE_SATURATION_THRESHOLD`` -- unchanged by SS-038 per the
    user's 2026-08-06 sign-off (keep the aggressive default, make it
    tunable, do not narrow it)."""

    value_threshold: float = 0.92
    saturation_threshold: float = 0.12


NEAR_WHITE_THRESHOLD_SPEC: ConfigSpec[NearWhiteThresholdConfig] = ConfigSpec(
    key="near_white_threshold",
    model=NearWhiteThresholdConfig,
    default=NearWhiteThresholdConfig(),
)


class EffortTierParams(BaseModel):
    """One effort tier's dial parameters -- the literal keyword arguments
    ``engine_v2_candidate_search.search_candidates()``/
    ``engine_v2_portfolio.select_portfolio()`` already accept. ``colour_mode``
    is documented metadata only -- see ``docs/tickets/SS-039-design.md``
    Open Question #3 (``BL-135``): no live stage reads it to select a
    colour-scoring algorithm."""

    search_pool_size: int  # -> search_candidates(top_k_bases=...)
    colour_mode: str  # documentation-only today -- NOT wired to any stage call (BL-135)
    mmr_lambda: float  # -> select_portfolio(lambda_=...)
    max_exploration: int  # -> select_portfolio(max_exploration=...)
    llm_candidate_count: (
        int | None
    )  # -> IStylingProvider.suggest_outfits(max_suggestions=...); None = no LLM call (E0)


class EngineV2EffortTierConfig(BaseModel):
    """Validates ``app_config.engine_v2_effort_tiers``. Values transcribed
    VERBATIM from the raw ticket's own E0-E2 table -- do not alter without
    product sign-off (docs/tickets/raw/SS-039.md)."""

    e0: EffortTierParams = EffortTierParams(
        search_pool_size=500,
        colour_mode="star",
        mmr_lambda=0.9,
        max_exploration=0,
        llm_candidate_count=None,
    )
    e1: EffortTierParams = EffortTierParams(
        search_pool_size=1500,
        colour_mode="pairwise",
        mmr_lambda=0.85,
        max_exploration=0,
        llm_candidate_count=5,
    )
    e2: EffortTierParams = EffortTierParams(
        search_pool_size=5000,
        colour_mode="pairwise_plus_volume",
        mmr_lambda=0.75,
        max_exploration=1,
        llm_candidate_count=6,
    )
    # Additive-only forward compat for a future E3/E4 ticket (AC #5's
    # "design note showing the planned shape"): that ticket adds
    #   e3: EffortTierParams | None = None
    #   e4: EffortTierParams | None = None
    # here -- Pydantic optional-field-with-default means every row already
    # seeded (this ticket's `018` included) still validates unchanged; no
    # migration, no AppConfigService.read() change, no existing consumer
    # breaks. EffortTierKey (engine_v2_effort_dial.py) only widens to
    # include "E3"/"E4" once that future ticket also adds the code path
    # that can return them.


ENGINE_V2_EFFORT_TIER_SPEC: ConfigSpec[EngineV2EffortTierConfig] = ConfigSpec(
    key="engine_v2_effort_tiers",
    model=EngineV2EffortTierConfig,
    default=EngineV2EffortTierConfig(),
)


class SuggestionNarrationCacheTtlConfig(BaseModel):
    """(SS-020) TTL for ``suggestion_narration_cache`` rows -- 6h coded
    default, same "missing/malformed row degrades to a safe default" posture
    as every other spec in this module."""

    seconds: int = 21600  # 6 hours


SUGGESTION_NARRATION_CACHE_TTL_SPEC: ConfigSpec[SuggestionNarrationCacheTtlConfig] = ConfigSpec(
    key="suggestion_narration_cache_ttl_seconds",
    model=SuggestionNarrationCacheTtlConfig,
    default=SuggestionNarrationCacheTtlConfig(),
)


class WeatherHeavyRainConfig(BaseModel):
    """(SS-022) The precipitation-rate half of the heavy-rain predicate
    (``services/weather_rules.is_heavy_rain``) -- an Architect inference
    (the commonly-cited "heavy rain" hourly rate), NOT a verified IMD/WMO
    standard, in the same unvalidated class as ``ENGINE_V2_RULE_WEIGHTS``.
    No seed migration: a missing/malformed row degrades to this coded
    default (SS-026's pattern, same as ``GEMINI_QUOTA_CEILING_SPEC``)."""

    precip_mm_per_hour: float = 7.6


WEATHER_HEAVY_RAIN_SPEC: ConfigSpec[WeatherHeavyRainConfig] = ConfigSpec(
    key="weather_heavy_rain_threshold",
    model=WeatherHeavyRainConfig,
    default=WeatherHeavyRainConfig(),
)


class RailPrecomputeDebounceConfig(BaseModel):
    """(SS-048) The debounce window ``services.rail_staleness
    .maybe_trigger_rail_recompute`` uses to decide whether a wardrobe write
    should schedule a ``suggestion_rails`` recompute. ``600`` (10 minutes)
    transcribed verbatim from ``docs/competitive/08-CHEAP-SUGGESTION-ENGINE.md``
    §5.2's own precompute-schedule table ("On wardrobe write (debounced ~10
    min)"), not invented. No seed migration -- a missing/malformed row
    degrades to this coded default, same posture as
    ``SuggestionNarrationCacheTtlConfig``."""

    seconds: int = 600


RAIL_PRECOMPUTE_DEBOUNCE_SPEC: ConfigSpec[RailPrecomputeDebounceConfig] = ConfigSpec(
    key="rail_precompute_debounce_seconds",
    model=RailPrecomputeDebounceConfig,
    default=RailPrecomputeDebounceConfig(),
)
