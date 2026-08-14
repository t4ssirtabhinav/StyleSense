"""Tests for backend/services/engine_v2_candidate_search.py (SS-038)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import get_args

import pytest

from ai.ports.interfaces import WardrobeCategory
from services.engine_v2_candidate_search import (
    _formality_item_score,
    assembly_slot_for,
    search_candidates,
)
from services.engine_v2_eligibility import resolve_styling_rules
from services.engine_v2_types import GarmentAttributes
from services.styling_rules_defaults import CATEGORY_FORMALITY, CATEGORY_SLOT
from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput

_AS_OF = date(2026, 7, 29)
_CATEGORIES: tuple[WardrobeCategory, ...] = get_args(WardrobeCategory)


def _item(
    id: str,
    *,
    category: WardrobeCategory = "ethnic_saree",
    color: str = "#8B0000",
) -> WardrobeItemInput:
    return WardrobeItemInput(id=id, category=category, color_primary=color)


def _occasion(
    *,
    key: str = "office",
    kind: str = "professional",
    formality: int = 6,
    styling_rules: dict | None = None,
) -> OccasionStylingInput:
    return OccasionStylingInput(
        key=key,
        kind=kind,  # type: ignore[arg-type]
        formality=formality,
        styling_rules=styling_rules or {},
    )


def _no_lookup(_category: str) -> GarmentAttributes | None:
    """A garment_lookup that always misses -- forces the fallback (CATEGORY_SLOT)
    path, exercising the AC's "same wardrobe fixture through both paths" case."""
    return None


def _fake_lookup_factory(
    rows: dict[str, GarmentAttributes],
) -> Callable[[str], GarmentAttributes | None]:
    def _lookup(category: str) -> GarmentAttributes | None:
        return rows.get(category.strip().lower())

    return _lookup


# ---------------------------------------------------------------------------
# assembly_slot_for
# ---------------------------------------------------------------------------


def test_assembly_slot_for_uses_garment_lookup_when_it_hits() -> None:
    attrs = GarmentAttributes(
        key="kurta",
        assembly_slot="top",
        garment_slot="torso_base",
        layer=0,
        register=("ethnic",),
        base_formality=4,
        pairs_with=(),
        requires_with=(),
        excludes_with=(),
    )
    item = _item("i1", category="ethnic_kurta")
    lookup = lambda category: attrs if category == "ethnic_kurta" else None  # noqa: E731
    assert assembly_slot_for(item, lookup) == "top"


def test_assembly_slot_for_falls_back_to_category_slot_when_lookup_misses() -> None:
    item = _item("i1", category="western_top")
    assert assembly_slot_for(item, _no_lookup) == CATEGORY_SLOT["western_top"]


def test_assembly_slot_for_raises_for_null_category() -> None:
    item = WardrobeItemInput(id="i1", category=None, color_primary="#8B0000")
    with pytest.raises(ValueError):
        assembly_slot_for(item, _no_lookup)


# ---------------------------------------------------------------------------
# search_candidates -- full cross product, no pre-cap
# ---------------------------------------------------------------------------


def test_total_base_pairs_considered_is_full_cross_product() -> None:
    tops = [_item(f"top{i}", category="western_top") for i in range(4)]
    bottoms = [_item(f"bottom{i}", category="western_bottom") for i in range(3)]
    one_pieces = [_item(f"dress{i}", category="western_dress") for i in range(2)]
    wardrobe = tops + bottoms + one_pieces

    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert result.total_base_pairs_considered == 4 * 3 + 2


def test_total_base_pairs_scales_with_wardrobe_size_not_flat() -> None:
    """Direct proof the old flat ~72 cap is gone -- total_base_pairs_considered
    grows with wardrobe size across [10, 30, 60, 120]-item wardrobes."""
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    counts = []
    for n in (10, 30, 60, 120):
        wardrobe = []
        for i in range(n):
            if i % 3 == 0:
                category: WardrobeCategory = "western_top"
            elif i % 3 == 1:
                category = "western_bottom"
            else:
                category = "western_dress"
            wardrobe.append(_item(f"item{i}", category=category))
        result = search_candidates(
            wardrobe,
            occasion=occasion,
            garment_lookup=_no_lookup,
            rules=rules,
            as_of=_AS_OF,
            season=None,
            style_preferences=None,
        )
        counts.append(result.total_base_pairs_considered)

    # Strictly increasing -- never flat at a fixed cap like the old ~72.
    assert counts == sorted(counts)
    assert len(set(counts)) == len(counts)
    assert counts[-1] > 72  # the old v0 cap, blown past


def test_search_candidates_uses_garment_lookup_assembly_slot() -> None:
    """A synthetic garment-types-shaped category resolves via garment_lookup,
    not CATEGORY_SLOT (which would KeyError on an unrecognised category)."""
    kurta_attrs = GarmentAttributes(
        key="kurta",
        assembly_slot="top",
        garment_slot="torso_base",
        layer=0,
        register=("ethnic",),
        base_formality=4,
        pairs_with=(),
        requires_with=(),
        excludes_with=(),
    )
    palazzo_attrs = GarmentAttributes(
        key="palazzo",
        assembly_slot="bottom",
        garment_slot="legs",
        layer=0,
        register=("ethnic",),
        base_formality=4,
        pairs_with=(),
        requires_with=(),
        excludes_with=(),
    )
    lookup = _fake_lookup_factory({"kurta": kurta_attrs, "palazzo": palazzo_attrs})

    top = WardrobeItemInput(id="top1", category="ethnic_kurta", color_primary="#1E3A8A")
    bottom = WardrobeItemInput(id="bottom1", category="ethnic_kurta", color_primary="#1E3A8A")

    # Force these two categories through the fake lookup via a monkeypatched
    # wrapper: real WardrobeCategory values never match "kurta"/"palazzo"
    # literally, so wrap lookup to translate for this synthetic test only.
    def wrapped_lookup(category: str) -> GarmentAttributes | None:
        mapping = {"ethnic_kurta": "kurta"}
        return lookup(mapping.get(category, category))

    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        [top, bottom],
        occasion=occasion,
        garment_lookup=wrapped_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    # Both items resolve to "top" via garment_lookup -- no valid top x bottom
    # base can form (missing_slots should include "bottom").
    assert "bottom" in result.missing_slots


# ---------------------------------------------------------------------------
# Top-N-per-remaining-slot expansion -- regression for "same shoe on every
# candidate"
# ---------------------------------------------------------------------------


def test_expansion_produces_multiple_distinct_footwear_choices() -> None:
    wardrobe = [
        _item("top1", category="western_top"),
        _item("bottom1", category="western_bottom"),
        _item("shoe1", category="footwear_casual", color="#000000"),
        _item("shoe2", category="footwear_formal", color="#111111"),
        _item("shoe3", category="footwear_sports", color="#222222"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    footwear_ids_seen: set[str] = set()
    for candidate in result.candidates:
        for item in candidate.items:
            if item.category in ("footwear_casual", "footwear_formal", "footwear_sports"):
                footwear_ids_seen.add(item.id)
    assert len(footwear_ids_seen) > 1, (
        "expected multiple distinct footwear choices across candidates"
    )


def test_expansion_produces_multiple_distinct_accessory_choices() -> None:
    wardrobe = [
        _item("saree1", category="ethnic_saree"),
        _item("shoe1", category="footwear_ethnic", color="#000000"),
        _item("jewel1", category="accessory_jewellery", color="#FFD700"),
        _item("jewel2", category="accessory_jewellery", color="#FFC0CB"),
        _item("jewel3", category="accessory_jewellery", color="#DAA520"),
    ]
    occasion = _occasion(key="ceremony_test", kind="ceremony", formality=8)
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    jewel_ids_seen: set[str] = set()
    for candidate in result.candidates:
        for item in candidate.items:
            if item.category == "accessory_jewellery":
                jewel_ids_seen.add(item.id)
    assert len(jewel_ids_seen) > 1


def test_missing_slots_computed_same_as_v0() -> None:
    wardrobe = [_item("saree1", category="ethnic_saree")]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert "footwear" in result.missing_slots
    assert "top" in result.missing_slots
    assert "bottom" in result.missing_slots
    assert "one_piece" not in result.missing_slots


def test_no_candidates_hallucinate_ids() -> None:
    wardrobe = [
        _item("top1", category="western_top"),
        _item("bottom1", category="western_bottom"),
        _item("shoe1", category="footwear_casual"),
    ]
    input_ids = {item.id for item in wardrobe}
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    for candidate in result.candidates:
        assert {item.id for item in candidate.items} <= input_ids


# ---------------------------------------------------------------------------
# AC #4 regression proof: zero-drift for enum-only wardrobes. Every real
# category today hits the fallback path (no live wardrobe_items.category
# value resolves through garment_types, per the design doc's own "Concrete
# values" note) -- this proves that fallback wiring is a genuine no-op
# relative to the pre-Engine-v2 CATEGORY_SLOT/CATEGORY_FORMALITY dicts, not
# merely assumed identical.
# ---------------------------------------------------------------------------


def test_fallback_path_is_a_genuine_noop_vs_direct_dict_lookups_for_every_category() -> None:
    occasion = _occasion(key="office", kind="professional", formality=6)
    for category in _CATEGORIES:  # every one of the 21 real WardrobeCategory values
        item = _item(f"item-{category}", category=category)
        assert assembly_slot_for(item, _no_lookup) == CATEGORY_SLOT[category]
        assert _formality_item_score(
            item, occasion.formality, tolerance=2
        ) == _direct_formality_score(category, occasion.formality, tolerance=2)


# ---------------------------------------------------------------------------
# SS-024: footwear_formality_mismatch gap flag (failure mode B -- a
# sneakers-only wardrobe at a ceremony/festival/religious occasion must not
# get sneakers with no signal at all).
# ---------------------------------------------------------------------------


def test_mismatched_footwear_sets_formality_mismatch_flag() -> None:
    """Ceremony occasion (footwear_required=True, preferred=[ethnic,
    formal]); the wardrobe's only footwear is footwear_sports. Every
    assembled candidate must carry the mismatch flag, AND the sneakers must
    still be present in items -- surfaced as a gap, never suppressed."""
    wardrobe = [
        _item("kurta1", category="ethnic_kurta"),
        _item("palazzo1", category="western_bottom"),
        _item("sneaker1", category="footwear_sports"),
    ]
    occasion = _occasion(key="ceremony_test", kind="ceremony", formality=8)
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert result.candidates, "expected at least one assembled candidate"
    for candidate in result.candidates:
        assert "footwear_formality_mismatch" in candidate.gap_flags
        assert any(item.id == "sneaker1" for item in candidate.items)


def test_preferred_footwear_sets_no_gap_flag() -> None:
    """Same occasion, wardrobe's footwear is in the preferred set (ethnic)
    -- no gap flag on a correct outfit (guards against a false-positive
    nudge)."""
    wardrobe = [
        _item("kurta1", category="ethnic_kurta"),
        _item("palazzo1", category="western_bottom"),
        _item("juti1", category="footwear_ethnic"),
    ]
    occasion = _occasion(key="ceremony_test", kind="ceremony", formality=8)
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert result.candidates
    for candidate in result.candidates:
        assert candidate.gap_flags == []


def test_footwear_gap_flags_are_mutually_exclusive() -> None:
    """No candidate ever carries both missing_footwear and
    footwear_formality_mismatch -- this is the assertion the narration
    payload's char-budget bound (BL-130) rests on."""
    wardrobe = [
        _item("kurta1", category="ethnic_kurta"),
        _item("palazzo1", category="western_bottom"),
        _item("sneaker1", category="footwear_sports"),
    ]
    occasion = _occasion(key="ceremony_test", kind="ceremony", formality=8)
    rules = resolve_styling_rules(occasion)
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert result.candidates
    for candidate in result.candidates:
        assert not (
            "missing_footwear" in candidate.gap_flags
            and "footwear_formality_mismatch" in candidate.gap_flags
        )


def test_no_mismatch_flag_when_occasion_has_no_preferred_footwear() -> None:
    """everyday kind: footwear_required=True but preferred_footwear_categories
    is unset -- guards the `and preferred_footwear` half of the gate."""
    wardrobe = [
        _item("top1", category="western_top"),
        _item("bottom1", category="western_bottom"),
        _item("sneaker1", category="footwear_sports"),
    ]
    occasion = _occasion(key="everyday_test", kind="everyday", formality=3)
    rules = resolve_styling_rules(occasion)
    assert not rules.preferred_footwear_categories
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert result.candidates
    for candidate in result.candidates:
        assert "footwear_formality_mismatch" not in candidate.gap_flags


def test_no_mismatch_flag_when_footwear_not_required() -> None:
    """footwear_required=False with a preference list still set (explicit
    override) -- guards the other half of the gate."""
    wardrobe = [
        _item("kurta1", category="ethnic_kurta"),
        _item("palazzo1", category="western_bottom"),
        _item("sneaker1", category="footwear_sports"),
    ]
    occasion = _occasion(
        key="ceremony_test",
        kind="ceremony",
        formality=8,
        styling_rules={"footwear_required": False},
    )
    rules = resolve_styling_rules(occasion)
    assert rules.footwear_required is False
    result = search_candidates(
        wardrobe,
        occasion=occasion,
        garment_lookup=_no_lookup,
        rules=rules,
        as_of=_AS_OF,
        season=None,
        style_preferences=None,
    )
    assert result.candidates
    for candidate in result.candidates:
        assert "footwear_formality_mismatch" not in candidate.gap_flags
        assert "missing_footwear" not in candidate.gap_flags


def _direct_formality_score(
    category: WardrobeCategory, occasion_formality: int, *, tolerance: int
) -> float:
    """The exact formula `_formality_item_score` implements, computed
    directly against `CATEGORY_FORMALITY`'s dict -- the independent
    "ground truth" this test compares the real function's fallback-path
    output against."""
    item_formality = CATEGORY_FORMALITY[category]
    distance = abs(item_formality - occasion_formality)
    if distance <= tolerance:
        return 1.0
    over = distance - tolerance
    return max(0.0, 1.0 - over / 5.0)
