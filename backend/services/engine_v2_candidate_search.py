"""SS-038 -- Engine v2 stage ② (candidate search), pure.

Scores the FULL base-pair space (not the old flat 8x8-per-slot cap), keeps
the top ``CANDIDATE_SEARCH_TOP_K_BASES`` (200), and expands each of the top
50 of those with the top ``CANDIDATE_SEARCH_TOP_N_PER_REMAINING_SLOT``
(default 5, not the single best) options per remaining slot. This is the
literal fix for two of ``styling_rules_engine.py``'s named gaps: colour was
absent from the old per-slot capping formula (now folded into the base-
ranking key below), and footwear/accessory/outerwear were a function of the
item alone so the same shoe/jacket/accessory appeared on every candidate
(now genuinely varied across the returned candidates for the same base).

**Expansion strategy -- a flagged Architect inference, not literally
specified by the design doc.** "Expand with the top N options per remaining
slot" is read here as ONE SLOT VARYING AT A TIME (footwear varies across its
top-N options while outerwear/accessory stay at their single best choice;
then outerwear varies while footwear/accessory stay best; etc.), not a full
cross-product across every remaining slot simultaneously. A full cross
product would be ``N ** (number of remaining slot dimensions)`` per base
(e.g. 5^4 = 625 for a ceremony/festival/religious occasion with two
preferred accessory categories) -- exponential and untested against any
stated performance bound. The one-slot-at-a-time approach still produces
"multiple distinct AssembledCandidates per base rather than one" (the
literal AC/test requirement) and scales linearly in the number of remaining
slots (``1 + sum(N_slot - 1)``), not exponentially. Flagged here rather
than silently chosen.

Per-item scoring primitives (``_formality_item_score``/``_recency_item_score``/
``_season_item_score``/``_occasion_tag_item_score``/
``_style_preference_item_bonus``) are moved verbatim from
``styling_rules_engine.py`` -- unchanged formulas, so stage② and stage③
share ONE implementation of each (no drift), same contract v0 already
established.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ai.ports.interfaces import SeasonTag, StylePreferencesInput
from services.engine_v2_colour import hue_distance_score, pairwise_colour_harmony
from services.engine_v2_types import AssembledCandidate, CandidateSearchResult, GarmentAttributes
from services.styling_rules_defaults import (
    CANDIDATE_SEARCH_COLOUR_WEIGHT,
    CANDIDATE_SEARCH_TOP_K_BASES,
    CANDIDATE_SEARCH_TOP_N_PER_REMAINING_SLOT,
    CATEGORY_FORMALITY,
    CATEGORY_SLOT,
)
from services.styling_rules_engine import _mean
from services.styling_rules_types import (
    OccasionStylingInput,
    StylingRulesOverride,
    WardrobeItemInput,
)

__all__ = ["assembly_slot_for", "search_candidates"]

_ALL_SLOTS: tuple[str, ...] = ("top", "bottom", "one_piece", "outerwear", "footwear", "accessory")
_DEFAULT_FORMALITY_TOLERANCE = 2

# The top N ranked bases (out of top_k_bases) that actually get expanded
# into multi-slot-variant AssembledCandidates -- an Architect-assigned
# constant transcribed from the design doc's own literal "the top 50 of
# those" wording, not independently tunable via styling_rules_defaults (the
# design doc names it inline, not among its "Concrete values" list of
# module-level constants).
_TOP_BASES_TO_EXPAND = 50


GarmentLookup = Callable[[str], GarmentAttributes | None]


# ---------------------------------------------------------------------------
# Per-item scoring primitives -- moved verbatim from styling_rules_engine.py
# ---------------------------------------------------------------------------


def _formality_item_score(
    item: WardrobeItemInput, occasion_formality: int, tolerance: int
) -> float:
    if item.category is None:
        return 0.5
    item_formality = CATEGORY_FORMALITY[item.category]
    distance = abs(item_formality - occasion_formality)
    if distance <= tolerance:
        return 1.0
    over = distance - tolerance
    return max(0.0, 1.0 - over / 5.0)


def _recency_item_score(item: WardrobeItemInput, as_of: date) -> float:
    """Favours under-worn items -- wear_count/last_worn_at vs as_of."""
    wear_count_score = 1.0 / (1.0 + max(0, item.wear_count))
    if item.last_worn_at is None:
        days_score = 1.0
    else:
        days_since = max(0, (as_of - item.last_worn_at).days)
        days_score = min(1.0, days_since / 90.0)
    return (wear_count_score + days_score) / 2.0


def _season_item_score(item: WardrobeItemInput, season: SeasonTag | None) -> float:
    if season is None:
        return 1.0
    if not item.season_tags:
        return 0.6  # unknown -- mild neutral, never a hard exclusion
    if season in item.season_tags or "all" in item.season_tags:
        return 1.0
    return 0.3


def _occasion_tag_item_score(item: WardrobeItemInput, occasion_key: str) -> float:
    """Additive-only, never gating."""
    return 1.0 if occasion_key in item.occasion_tags else 0.0


def _style_preference_item_bonus(
    item: WardrobeItemInput, style_preferences: StylePreferencesInput | None
) -> float:
    if style_preferences is None or item.color_primary is None:
        return 0.0
    favourites = style_preferences.favourite_colours or []
    for fav_hex in favourites:
        if hue_distance_score(item.color_primary, fav_hex) >= 0.85:
            return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assembly_slot_for(item: WardrobeItemInput, garment_lookup: GarmentLookup) -> str:
    """Resolves via ``garment_lookup(item.category)`` -> ``GarmentAttributes.assembly_slot``
    when a row exists, else ``CATEGORY_SLOT[item.category]`` (the existing
    21-value dict). This is the fallback boundary the AC's regression test
    targets. Requires a non-``None`` category -- eligibility (stage①) has
    already filtered those out before this stage ever sees an item."""
    if item.category is None:
        raise ValueError(
            "assembly_slot_for requires a non-null category -- eligibility must run first"
        )
    resolved = garment_lookup(item.category)
    if resolved is not None:
        return resolved.assembly_slot
    return CATEGORY_SLOT[item.category]


def search_candidates(
    eligible_items: list[WardrobeItemInput],
    *,
    occasion: OccasionStylingInput,
    garment_lookup: GarmentLookup,
    rules: StylingRulesOverride,
    as_of: date,
    season: SeasonTag | None,
    style_preferences: StylePreferencesInput | None,
    top_k_bases: int = CANDIDATE_SEARCH_TOP_K_BASES,
    top_n_per_remaining_slot: int = CANDIDATE_SEARCH_TOP_N_PER_REMAINING_SLOT,
) -> CandidateSearchResult:
    """Doc-internal gap-fill, flagged explicitly (not a divergence from
    anything the design doc says explicitly): the design doc's own listed
    signature for this function, and its orchestrator call-site example,
    both omit an ``occasion`` parameter -- but the base-ranking formula the
    same doc specifies two lines above ("0.35*mean(formality) + ... +
    0.15*mean(occasion_tag)...") structurally requires
    ``occasion.formality``/``occasion.key``, which nothing else in this
    function's other parameters carries (``rules: StylingRulesOverride`` has
    no formality-target field). Added as the minimal, spec-consistent way to
    satisfy the doc's own formula -- mirrors ``IWardrobeRepository.item_exists``'s
    precedent for this exact class of doc-internal gap.
    """
    grouped: dict[str, list[WardrobeItemInput]] = {slot: [] for slot in _ALL_SLOTS}
    for item in eligible_items:
        grouped[assembly_slot_for(item, garment_lookup)].append(item)

    missing_slots = sorted(slot for slot in _ALL_SLOTS if not grouped[slot])

    tops = grouped["top"]
    bottoms = grouped["bottom"]
    one_pieces = grouped["one_piece"]

    # Diagnostic, UNCAPPED -- the property test's proof target that
    # candidate count scales with wardrobe size rather than staying flat at
    # the old ~72 cap. Computed independent of `rules.required_base` -- it
    # counts every base the wardrobe COULD form, not just the ones actually
    # built below.
    total_base_pairs_considered = len(tops) * len(bottoms) + len(one_pieces)

    tolerance = (
        rules.formality_tolerance
        if rules.formality_tolerance is not None
        else _DEFAULT_FORMALITY_TOLERANCE
    )

    def item_score(item: WardrobeItemInput) -> float:
        return (
            0.35 * _formality_item_score(item, occasion.formality, tolerance)
            + 0.25 * _recency_item_score(item, as_of)
            + 0.15 * _season_item_score(item, season)
            + 0.15 * _occasion_tag_item_score(item, occasion.key)
            + 0.10 * _style_preference_item_bonus(item, style_preferences)
        )

    def base_key(items: list[WardrobeItemInput]) -> float:
        return (
            0.35
            * _mean(
                [_formality_item_score(i, occasion.formality, tolerance) for i in items],
                default=0.0,
            )
            + 0.25 * _mean([_recency_item_score(i, as_of) for i in items], default=0.0)
            + 0.15 * _mean([_season_item_score(i, season) for i in items], default=1.0)
            + 0.15 * _mean([_occasion_tag_item_score(i, occasion.key) for i in items], default=0.0)
            + 0.10
            * _mean(
                [_style_preference_item_bonus(i, style_preferences) for i in items], default=0.0
            )
            + CANDIDATE_SEARCH_COLOUR_WEIGHT * pairwise_colour_harmony(items)
        )

    required_base = rules.required_base or "either"
    bases: list[list[WardrobeItemInput]] = []
    if required_base in ("one_piece", "either"):
        for item in one_pieces:
            bases.append([item])
    if required_base in ("top_bottom", "either"):
        for top in tops:
            for bottom in bottoms:
                bases.append([top, bottom])

    ranked_bases = sorted(bases, key=lambda b: (-base_key(b), tuple(sorted(i.id for i in b))))
    kept_bases = ranked_bases[:top_k_bases]
    bases_to_expand = kept_bases[:_TOP_BASES_TO_EXPAND]

    preferred_footwear = set(rules.preferred_footwear_categories or [])
    preferred_accessory = set(rules.preferred_accessory_categories or [])

    def footwear_key(item: WardrobeItemInput) -> float:
        bonus = 0.2 if item.category in preferred_footwear else 0.0
        return item_score(item) + bonus

    def accessory_key(item: WardrobeItemInput) -> float:
        bonus = 0.2 if item.category in preferred_accessory else 0.0
        return item_score(item) + bonus

    footwear_ranked = sorted(grouped["footwear"], key=lambda i: (-footwear_key(i), i.id))
    outerwear_ranked = sorted(grouped["outerwear"], key=lambda i: (-item_score(i), i.id))
    accessory_ranked_by_category: dict[str, list[WardrobeItemInput]] = {}
    for category in sorted(preferred_accessory):
        category_options = [i for i in grouped["accessory"] if i.category == category]
        accessory_ranked_by_category[category] = sorted(
            category_options, key=lambda i: (-accessory_key(i), i.id)
        )

    footwear_topn = footwear_ranked[:top_n_per_remaining_slot]
    outerwear_topn = outerwear_ranked[:top_n_per_remaining_slot]
    accessory_topn_by_category = {
        category: items[:top_n_per_remaining_slot]
        for category, items in accessory_ranked_by_category.items()
    }

    assembled: list[AssembledCandidate] = []
    seen_item_sets: set[frozenset[str]] = set()

    for base in bases_to_expand:
        # The "best of everything" variant: rank-1 in every remaining slot.
        best_footwear = footwear_topn[0] if footwear_topn else None
        best_outerwear = outerwear_topn[0] if outerwear_topn else None
        best_accessory_by_category = {
            category: items[0] for category, items in accessory_topn_by_category.items() if items
        }

        def build(
            footwear: WardrobeItemInput | None,
            outerwear: WardrobeItemInput | None,
            accessories: dict[str, WardrobeItemInput],
            base: list[WardrobeItemInput] = base,
        ) -> AssembledCandidate:
            items = list(base)
            gap_flags: list[str] = []
            if footwear is not None:
                items.append(footwear)
                # SS-024: the ranking bonus at footwear_key() above only
                # *biases* footwear selection toward preferred_footwear --
                # it never excludes non-preferred footwear (a sneakers-only
                # wardrobe still has to wear something). When the occasion
                # both requires footwear AND expresses a preference, and the
                # footwear actually attached isn't in that preference set,
                # surface it rather than silently forcing the mismatch (the
                # ticket's own "sneakers-only + wedding_guest" failure
                # mode). Gated identically to the existing 0.7-component
                # penalty in engine_v2_attribute_scoring.py -- no new
                # semantics, just a visible flag for a judgment the engine
                # already makes. Mutually exclusive with missing_footwear
                # by construction (different branches of this if).
                if (
                    rules.footwear_required
                    and preferred_footwear
                    and footwear.category not in preferred_footwear
                ):
                    gap_flags.append("footwear_formality_mismatch")
            elif rules.footwear_required:
                gap_flags.append("missing_footwear")
            if outerwear is not None:
                items.append(outerwear)
            elif rules.outerwear_required:
                gap_flags.append("missing_outerwear")
            for category in sorted(accessories):
                items.append(accessories[category])
            return AssembledCandidate(items=items, gap_flags=gap_flags)

        def add(candidate: AssembledCandidate) -> None:
            key = frozenset(i.id for i in candidate.items)
            if key in seen_item_sets:
                return
            seen_item_sets.add(key)
            assembled.append(candidate)

        # 1. The single "all-best" variant.
        add(build(best_footwear, best_outerwear, best_accessory_by_category))

        # 2. Vary footwear alone across its top-N (others held at best).
        for option in footwear_topn[1:]:
            add(build(option, best_outerwear, best_accessory_by_category))

        # 3. Vary outerwear alone across its top-N (others held at best).
        for option in outerwear_topn[1:]:
            add(build(best_footwear, option, best_accessory_by_category))

        # 4. Vary one accessory category at a time across its top-N.
        for category, options in accessory_topn_by_category.items():
            for option in options[1:]:
                varied = dict(best_accessory_by_category)
                varied[category] = option
                add(build(best_footwear, best_outerwear, varied))

    return CandidateSearchResult(
        candidates=assembled,
        total_base_pairs_considered=total_base_pairs_considered,
        missing_slots=missing_slots,
    )
