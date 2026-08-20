"""SS-038 -- Engine v2 stage ① (eligibility), pure.

Hard constraints only: dedupe, missing-category/colour exclusion, hard
colour-family exclusion (including the near-white guard, now app_config-
backed -- resolves ``BL-111``). Mostly a refactor of what SS-027/037 already
built, pulled into its own explicit stage rather than mixed into scoring.

``resolve_styling_rules``/``_dedupe_by_id``'s logic is moved verbatim from
``styling_rules_engine.py``'s former ``_resolve_styling_rules``/
``_dedupe_by_id``.
"""

from __future__ import annotations

from typing import Any

from services.app_config import AppConfigSnapshot, app_config_service
from services.app_config_specs import NEAR_WHITE_THRESHOLD_SPEC, NearWhiteThresholdConfig
from services.engine_v2_colour import item_is_hard_excluded_white
from services.engine_v2_types import EligibilityResult
from services.styling_rules_defaults import HARD_EXCLUDED_COLOR_FAMILIES, default_styling_rules_for
from services.styling_rules_types import (
    OccasionStylingInput,
    StylingRulesOverride,
    WardrobeItemInput,
)
from services.weather_rules import (
    WeatherContext,
    weather_excluded_color_families,
    weather_excluded_fabrics,
)

__all__ = ["resolve_styling_rules", "resolve_near_white_thresholds", "filter_eligible"]


def resolve_styling_rules(occasion: OccasionStylingInput) -> StylingRulesOverride:
    """Parses ``occasion.styling_rules``, degrades to
    ``default_styling_rules_for(occasion.kind)`` on empty/unparseable
    fields, then layers any successfully-parsed override field on top of
    that base -- partial overrides work (e.g. a hand-edited
    ``{"formality_tolerance": 0}`` only changes that one field). Moved
    verbatim from ``styling_rules_engine._resolve_styling_rules``."""
    base = default_styling_rules_for(occasion.kind)
    parsed = StylingRulesOverride.parse_lenient(occasion.styling_rules)
    merged: dict[str, Any] = {}
    for name in StylingRulesOverride.model_fields:
        value = getattr(parsed, name)
        merged[name] = value if value is not None else getattr(base, name)
    return StylingRulesOverride(**merged)


def resolve_near_white_thresholds(
    snapshot: AppConfigSnapshot, resolved_rules: StylingRulesOverride
) -> NearWhiteThresholdConfig:
    """Pure given the already-fetched ``snapshot`` (``app_config_service.read``
    is itself synchronous/pure -- only the caller's earlier ``.snapshot()``
    call was async). Per-field: an occasion override
    (``resolved_rules.near_white_value_threshold``/
    ``near_white_saturation_threshold``) wins when non-``None``, else the
    app_config value (which itself degrades to the coded default 0.92/0.12
    when the row is missing/malformed -- SS-026's pattern)."""
    app_config_value = app_config_service.read(snapshot, NEAR_WHITE_THRESHOLD_SPEC)
    value_threshold = (
        resolved_rules.near_white_value_threshold
        if resolved_rules.near_white_value_threshold is not None
        else app_config_value.value_threshold
    )
    saturation_threshold = (
        resolved_rules.near_white_saturation_threshold
        if resolved_rules.near_white_saturation_threshold is not None
        else app_config_value.saturation_threshold
    )
    return NearWhiteThresholdConfig(
        value_threshold=value_threshold, saturation_threshold=saturation_threshold
    )


def _dedupe_by_id(wardrobe: list[WardrobeItemInput]) -> list[WardrobeItemInput]:
    """A caller bug or test fixture could construct duplicate ids (the real
    DB PK prevents this) -- dedupe by id, keep first occurrence, rather than
    let a duplicate silently double-count in a candidate. Moved verbatim
    from ``styling_rules_engine._dedupe_by_id``."""
    seen: set[str] = set()
    result: list[WardrobeItemInput] = []
    for item in wardrobe:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result


def filter_eligible(
    wardrobe: list[WardrobeItemInput],
    occasion: OccasionStylingInput,
    rules: StylingRulesOverride,
    *,
    near_white_thresholds: NearWhiteThresholdConfig,
    weather: WeatherContext | None = None,
) -> EligibilityResult:
    """Dedupe-by-id, missing-category/colour exclusion count, hard-colour-
    family exclusion (``HARD_EXCLUDED_COLOR_FAMILIES`` merged with
    ``rules.excluded_color_families``, unchanged), near-white filter using
    the resolved thresholds via ``engine_v2_colour.item_is_hard_excluded_white``.

    (SS-022) ``weather`` is additive, default ``None`` -- reproduces
    pre-SS-022 output byte-for-byte. When ``weather.is_heavy_rain``: white
    (including near-white/cream/ivory, via the SAME ``item_is_hard_excluded_white``
    call as ``wedding_guest`` -- no second definition of "white") and
    ``fabric == "silk"`` (exact, case-insensitive match) are excluded, in
    addition to whatever the occasion already excludes. Mandatory
    relax-if-empty guardrail (design §3 step 3): if the post-weather set is
    empty and the pre-weather set was non-empty, the weather exclusions are
    discarded entirely and ``weather_exclusions_relaxed=True`` is returned.

    (SS-040) Lifecycle exclusion (``do_not_style``/``is_archived``) runs
    FIRST, before the missing-category/colour count -- an archived item
    that also lacks a category must not be counted in
    ``excluded_missing_color_or_category``. Single ``not (do_not_style or
    is_archived)`` predicate: an item with both flags is removed once and
    counted once in ``excluded_lifecycle``. Lifecycle exclusions are NEVER
    relaxed by the weather guardrail below -- ``pre_weather`` is derived
    from the already-lifecycle-filtered pool, so the relax-if-empty
    fallback can never resurrect a do-not-style/archived item. The user's
    explicit instruction beats the engine's weather inference."""
    deduped = _dedupe_by_id(wardrobe)

    stylable = [item for item in deduped if not (item.do_not_style or item.is_archived)]
    excluded_lifecycle = len(deduped) - len(stylable)

    excluded_missing = sum(
        1 for item in stylable if item.category is None or item.color_primary is None
    )
    missing_filtered = [
        item for item in stylable if item.category is not None and item.color_primary is not None
    ]

    hard_families = HARD_EXCLUDED_COLOR_FAMILIES.get(occasion.key, frozenset())
    effective_excluded = set(rules.excluded_color_families or []) | hard_families

    def _white_filtered(
        pool: list[WardrobeItemInput], excluded: set[str]
    ) -> list[WardrobeItemInput]:
        if "white" not in excluded:
            return pool
        # Code-level, unconditional guard (never a prompt-level instruction)
        # -- applied regardless of what styling_rules contains or omits.
        return [
            item
            for item in pool
            if not item_is_hard_excluded_white(
                item,
                value_threshold=near_white_thresholds.value_threshold,
                saturation_threshold=near_white_thresholds.saturation_threshold,
            )
        ]

    # "Everything currently in this function running unchanged" -- the
    # pre-SS-022 result, ignoring weather entirely. This is what the
    # relax-if-empty guardrail falls back to (design §3 step 3), NOT the
    # weather-influenced white-only intermediate.
    pre_weather = _white_filtered(missing_filtered, effective_excluded)

    eligible = pre_weather
    weather_exclusions_relaxed = False
    if weather is not None and weather.is_heavy_rain:
        weather_excluded = effective_excluded | weather_excluded_color_families(weather)
        eligible = _white_filtered(missing_filtered, weather_excluded)

        excluded_fabrics = weather_excluded_fabrics(weather)
        if excluded_fabrics:
            eligible = [
                item
                for item in eligible
                if item.fabric is None or item.fabric.casefold() not in excluded_fabrics
            ]

        if not eligible and pre_weather:
            # Relax-if-empty (design §3 step 3): a monsoon user whose
            # wardrobe is mostly white/silk must still get suggestions --
            # degraded advice beats an empty screen. Deliberately
            # all-or-nothing at the item-pool level, not per-slot.
            eligible = pre_weather
            weather_exclusions_relaxed = True

    return EligibilityResult(
        eligible_items=eligible,
        excluded_missing_color_or_category=excluded_missing,
        weather_exclusions_relaxed=weather_exclusions_relaxed,
        excluded_lifecycle=excluded_lifecycle,
    )
