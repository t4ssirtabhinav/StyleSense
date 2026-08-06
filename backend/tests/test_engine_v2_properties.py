"""Property-based boundary sweep for Engine v2 (SS-038), migrated from
``test_styling_rules_properties.py`` -- each changed assertion carries its
own one-line justification per SS-037's precedent for touching shipped
test assertions.

Re-points the "never hallucinates ids" / "deterministic" / "wedding_guest
white rule" properties at the pure Engine v2 pipeline (``filter_eligible`` +
``search_candidates`` + ``score_assembled_candidate`` + ``select_portfolio``)
instead of the now-deleted ``styling_rules_engine.generate_candidates``.
Adds one NEW property this ticket's AC requires: candidate count
(``total_base_pairs_considered``) scales with wardrobe size across
``[10, 30, 60, 120]``-item synthetic wardrobes and is NOT flat at the old
~72 cap.

``hypothesis`` is already a repo dependency (added by SS-027's own property
test file, ``hypothesis==6.163.0``).
"""

from __future__ import annotations

import copy
from datetime import date
from typing import get_args

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ai.ports.interfaces import WardrobeCategory
from services.app_config_specs import NearWhiteThresholdConfig
from services.engine_v2_attribute_scoring import score_assembled_candidate
from services.engine_v2_candidate_search import search_candidates
from services.engine_v2_eligibility import filter_eligible, resolve_styling_rules
from services.engine_v2_portfolio import select_portfolio
from services.engine_v2_types import GarmentAttributes, NoveltyInputs
from services.styling_rules_defaults import DEFAULT_SCORE_FLOOR
from services.styling_rules_types import (
    GapReport,
    OccasionKind,
    OccasionStylingInput,
    ScoredCandidate,
    WardrobeItemInput,
)

_AS_OF = date(2026, 7, 29)
_CATEGORIES = list(get_args(WardrobeCategory))
_KINDS = list(get_args(OccasionKind))
_HERO_CATEGORIES = ("ethnic_saree", "western_top", "western_bottom", "ethnic_lehenga")
_CODED_DEFAULT_NEAR_WHITE = NearWhiteThresholdConfig()


def _no_lookup(_category: str) -> GarmentAttributes | None:
    return None


def _run_pipeline(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput
) -> list[ScoredCandidate]:
    """Runs stage①->②->③ (no I/O) end to end -- everything
    ``EngineV2.generate_portfolio`` does minus the two async calls
    (garment registry refresh, novelty fetch), which this property sweep
    substitutes with a never-hit lookup and an empty ``NoveltyInputs``."""
    rules = resolve_styling_rules(occasion)
    eligibility = filter_eligible(
        wardrobe, occasion, rules, near_white_thresholds=_CODED_DEFAULT_NEAR_WHITE
    )
    search_result = search_candidates(
        eligibility.eligible_items,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    scored = [
        score_assembled_candidate(
            candidate,
            occasion,
            rules,
            garment_lookup=_no_lookup,
            fabric_attrs={},
            novelty_inputs=NoveltyInputs(),
            as_of=_AS_OF,
            season=None,
            style_preferences=None,
        )
        for candidate in search_result.candidates
    ]
    return scored


_hex_color_strategy = st.builds(
    lambda r, g, b: f"#{r:02X}{g:02X}{b:02X}",
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
)

_item_strategy = st.builds(
    WardrobeItemInput,
    id=st.uuids().map(str),
    category=st.sampled_from(_CATEGORIES),
    color_primary=_hex_color_strategy,
    wear_count=st.integers(min_value=0, max_value=50),
    last_worn_at=st.none()
    | st.dates(min_value=date(2020, 1, 1), max_value=date(2026, 12, 31)),
)

# Kept deliberately smaller than SS-027's old max_size=60: Engine v2's wide
# search + top-N-per-remaining-slot expansion is intentionally much more
# combinatorially expensive per wardrobe than v0's flat ~72-candidate cap --
# a smaller max_size keeps this hypothesis sweep's wall-clock reasonable
# while still exercising real combinatorics (unlike v0, size alone already
# varies total_base_pairs_considered meaningfully at this scale).
_wardrobe_strategy = st.lists(_item_strategy, min_size=0, max_size=30, unique_by=lambda i: i.id)

_occasion_key_strategy = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12)

_occasion_strategy = st.builds(
    OccasionStylingInput,
    key=_occasion_key_strategy,
    kind=st.sampled_from(_KINDS),
    formality=st.integers(min_value=0, max_value=10),
)

_default_settings = settings(
    max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


@_default_settings
@given(wardrobe=_wardrobe_strategy, occasion=_occasion_strategy)
def test_property_never_hallucinates_ids_across_random_wardrobes(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput
) -> None:
    # CHANGED from generate_candidates(...).candidates to the Engine v2
    # pipeline's scored candidates -- generate_candidates no longer exists
    # (moved into engine_v2_candidate_search.search_candidates +
    # engine_v2_attribute_scoring.score_assembled_candidate, SS-038).
    input_ids = {item.id for item in wardrobe}
    scored = _run_pipeline(wardrobe, occasion)
    for candidate in scored:
        assert set(candidate.item_ids) <= input_ids


@_default_settings
@given(wardrobe=_wardrobe_strategy, occasion=_occasion_strategy)
def test_property_deterministic_across_repeated_runs(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput
) -> None:
    # CHANGED to call the Engine v2 pipeline twice on deep-copied inputs
    # instead of generate_candidates (deleted, SS-038) -- same determinism
    # property, new call surface.
    wardrobe2 = copy.deepcopy(wardrobe)
    occasion2 = occasion.model_copy(deep=True)

    scored1 = _run_pipeline(wardrobe, occasion)
    scored2 = _run_pipeline(wardrobe2, occasion2)

    dump1 = [c.model_dump() for c in scored1]
    dump2 = [c.model_dump() for c in scored2]
    assert dump1 == dump2


_white_item_strategy = st.builds(
    WardrobeItemInput,
    id=st.uuids().map(str),
    category=st.sampled_from(_HERO_CATEGORIES),
    color_primary=st.sampled_from(
        ["#FFFFFF", "#FFFEFE", "#FEFEFE", "#FFFFFE", "white", "off white", "ivory", "snow"]
    ),
    wear_count=st.integers(min_value=0, max_value=10),
)

_all_white_wardrobe_strategy = st.lists(
    _white_item_strategy, min_size=1, max_size=10, unique_by=lambda i: i.id
)


@_default_settings
@given(wardrobe=_all_white_wardrobe_strategy)
def test_property_wedding_guest_white_rule_holds_across_random_colors(
    wardrobe: list[WardrobeItemInput],
) -> None:
    # CHANGED to call filter_eligible directly (stage①, the actual home of
    # the near-white hard exclusion in Engine v2) instead of
    # generate_candidates (deleted, SS-038) -- same property, new call
    # surface; coded-default thresholds (config row absent) used explicitly.
    occasion = OccasionStylingInput(key="wedding_guest", kind="ceremony", formality=9)
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(
        wardrobe, occasion, rules, near_white_thresholds=_CODED_DEFAULT_NEAR_WHITE
    )
    eligible_ids = {item.id for item in result.eligible_items}
    hero_ids = {item.id for item in wardrobe if item.category in _HERO_CATEGORIES}
    assert not (eligible_ids & hero_ids)


@_default_settings
@given(wardrobe=_wardrobe_strategy, occasion=_occasion_strategy)
def test_property_portfolio_never_exceeds_max_size_and_never_below_floor(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput
) -> None:
    # CHANGED/NEW: v0's test_property_candidate_count_never_exceeds_max_candidates
    # asserted against generate_candidates(max_candidates=...) (deleted,
    # SS-038's replacement concept is select_portfolio's portfolio_size_range
    # + max_exploration, not a single max_candidates cap) -- re-expressed
    # against the new portfolio-selection surface: never exceeds 8 main +
    # 2 exploration, and every selected candidate is >= score_floor.
    scored = _run_pipeline(wardrobe, occasion)
    result = select_portfolio(
        scored,
        score_floor=DEFAULT_SCORE_FLOOR,
        lambda_=0.75,
        gap_report=GapReport(),
    )
    main = [pc for pc in result.portfolio if not pc.is_exploration]
    exploration = [pc for pc in result.portfolio if pc.is_exploration]
    assert len(main) <= 8
    assert len(exploration) <= 2
    for pc in result.portfolio:
        assert pc.candidate.total_score >= DEFAULT_SCORE_FLOOR


# ---------------------------------------------------------------------------
# NEW property (this ticket's own AC): candidate count scales with wardrobe
# size, not flat at the old ~72 cap.
# ---------------------------------------------------------------------------


def _synthetic_wardrobe(n: int) -> list[WardrobeItemInput]:
    items = []
    for i in range(n):
        if i % 3 == 0:
            category: WardrobeCategory = "western_top"
        elif i % 3 == 1:
            category = "western_bottom"
        else:
            category = "western_dress"
        items.append(
            WardrobeItemInput(id=f"item-{i}", category=category, color_primary="#8B0000")
        )
    return items


def test_property_candidate_count_scales_with_wardrobe_size_not_flat_at_old_cap() -> None:
    occasion = OccasionStylingInput(key="office", kind="professional", formality=6)
    rules = resolve_styling_rules(occasion)
    counts = []
    for n in (10, 30, 60, 120):
        wardrobe = _synthetic_wardrobe(n)
        eligibility = filter_eligible(
            wardrobe, occasion, rules, near_white_thresholds=_CODED_DEFAULT_NEAR_WHITE
        )
        result = search_candidates(
            eligibility.eligible_items,
            occasion=occasion,
            garment_lookup=_no_lookup,
            rules=rules,
            as_of=_AS_OF,
            season=None,
            style_preferences=None,
        )
        counts.append(result.total_base_pairs_considered)

    assert counts == sorted(counts), f"expected non-decreasing counts, got {counts}"
    assert len(set(counts)) == len(counts), f"expected strictly increasing counts, got {counts}"
    assert counts[-1] > 72, "candidate count must scale past the old v0 flat ~72 cap"
