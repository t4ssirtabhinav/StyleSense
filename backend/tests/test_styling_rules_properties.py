"""Property-based boundary sweep for backend/services/styling_rules_engine.py
(SS-027) -- satisfies the AC's literal "Property-tested" wording with real
generated-input coverage rather than a fixed table of examples.

``hypothesis`` was not in ``backend/requirements.txt`` before this ticket;
added as a test-only dependency (zero production risk), resolved version
``hypothesis==6.163.0`` (pulls in ``sortedcontainers==2.4.0``), recorded in
``requirements.txt`` and the worklog per the design doc's recommendation.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import get_args

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ai.ports.interfaces import WardrobeCategory
from services.styling_rules_engine import generate_candidates
from services.styling_rules_types import OccasionKind, OccasionStylingInput, WardrobeItemInput

_AS_OF = date(2026, 7, 29)
_CATEGORIES = list(get_args(WardrobeCategory))
_KINDS = list(get_args(OccasionKind))
_HERO_CATEGORIES = ("ethnic_saree", "western_top", "western_bottom", "ethnic_lehenga")

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

_wardrobe_strategy = st.lists(
    _item_strategy, min_size=0, max_size=60, unique_by=lambda i: i.id
)

_occasion_key_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12
)

_occasion_strategy = st.builds(
    OccasionStylingInput,
    key=_occasion_key_strategy,
    kind=st.sampled_from(_KINDS),
    formality=st.integers(min_value=0, max_value=10),
)

_default_settings = settings(
    max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


@_default_settings
@given(wardrobe=_wardrobe_strategy, occasion=_occasion_strategy)
def test_property_never_hallucinates_ids_across_random_wardrobes(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput
) -> None:
    input_ids = {item.id for item in wardrobe}
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    for candidate in result.candidates:
        assert set(candidate.item_ids) <= input_ids


@_default_settings
@given(wardrobe=_wardrobe_strategy, occasion=_occasion_strategy)
def test_property_deterministic_across_repeated_runs(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput
) -> None:
    wardrobe2 = copy.deepcopy(wardrobe)
    occasion2 = occasion.model_copy(deep=True)

    r1 = generate_candidates(wardrobe, occasion, as_of=_AS_OF, season="summer")
    r2 = generate_candidates(wardrobe2, occasion2, as_of=_AS_OF, season="summer")

    assert r1.model_dump() == r2.model_dump()


_white_item_strategy = st.builds(
    WardrobeItemInput,
    id=st.uuids().map(str),
    category=st.sampled_from(_HERO_CATEGORIES),
    color_primary=st.sampled_from(["#FFFFFF", "#FFFEFE", "#FEFEFE", "#FFFFFE"]),
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
    occasion = OccasionStylingInput(key="wedding_guest", kind="ceremony", formality=9)
    result = generate_candidates(wardrobe, occasion, as_of=_AS_OF)
    hero_ids = {item.id for item in wardrobe if item.category in _HERO_CATEGORIES}
    for candidate in result.candidates:
        assert not (set(candidate.item_ids) & hero_ids)


@_default_settings
@given(
    wardrobe=_wardrobe_strategy,
    occasion=_occasion_strategy,
    max_candidates=st.integers(min_value=1, max_value=10),
)
def test_property_candidate_count_never_exceeds_max_candidates(
    wardrobe: list[WardrobeItemInput], occasion: OccasionStylingInput, max_candidates: int
) -> None:
    result = generate_candidates(
        wardrobe, occasion, as_of=_AS_OF, max_candidates=max_candidates
    )
    assert len(result.candidates) <= max_candidates
