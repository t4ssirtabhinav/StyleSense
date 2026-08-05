"""Tests for backend/services/styling_rules_defaults.py (SS-027)."""

from __future__ import annotations

from typing import get_args

from ai.ports.interfaces import WardrobeCategory
from services.styling_rules_defaults import (
    CATEGORY_FORMALITY,
    CATEGORY_SLOT,
    DEFAULT_STYLING_RULES_BY_KIND,
    HARD_EXCLUDED_COLOR_FAMILIES,
)
from services.styling_rules_types import OccasionKind


def test_category_slot_covers_every_wardrobe_category() -> None:
    """Iterates WardrobeCategory.__args__, not a hardcoded count -- fails
    loudly if the Literal is ever widened without updating this table."""
    for category in get_args(WardrobeCategory):
        assert category in CATEGORY_SLOT, f"{category} missing from CATEGORY_SLOT"
    assert len(CATEGORY_SLOT) == len(get_args(WardrobeCategory))


def test_category_formality_covers_every_wardrobe_category() -> None:
    for category in get_args(WardrobeCategory):
        assert category in CATEGORY_FORMALITY, f"{category} missing from CATEGORY_FORMALITY"
    assert len(CATEGORY_FORMALITY) == len(get_args(WardrobeCategory))


def test_default_styling_rules_covers_every_occasion_kind() -> None:
    for kind in get_args(OccasionKind):
        assert kind in DEFAULT_STYLING_RULES_BY_KIND, f"{kind} missing from defaults"
    assert len(DEFAULT_STYLING_RULES_BY_KIND) == len(get_args(OccasionKind))


def test_hard_excluded_color_families_contains_wedding_guest_white() -> None:
    """Guards against accidental deletion during a future refactor -- this
    directly transcribes CLAUDE.md's own India-Specific rule ("never suggest
    white for wedding_guest")."""
    assert HARD_EXCLUDED_COLOR_FAMILIES["wedding_guest"] == frozenset({"white"})


def test_category_slot_values_are_one_of_the_six_known_slots() -> None:
    known_slots = {"top", "bottom", "one_piece", "outerwear", "footwear", "accessory"}
    assert set(CATEGORY_SLOT.values()) <= known_slots


def test_category_formality_values_within_0_to_10_range() -> None:
    for value in CATEGORY_FORMALITY.values():
        assert 0 <= value <= 10


# ---------------------------------------------------------------------------
# SS-037 Bug 3 -- dupatta attachability data change
# ---------------------------------------------------------------------------


def test_ceremony_festival_religious_preferred_accessories_include_ethnic_dupatta() -> None:
    for kind in ("ceremony", "festival", "religious"):
        categories = DEFAULT_STYLING_RULES_BY_KIND[kind].preferred_accessory_categories
        assert categories is not None
        assert "accessory_jewellery" in categories
        assert "ethnic_dupatta" in categories


def test_other_kinds_preferred_accessories_unchanged() -> None:
    """Regression guard: the 6 kinds untouched by SS-037's Bug 3 fix keep
    preferred_accessory_categories unset (None)."""
    untouched_kinds = ("everyday", "travel", "social", "milestone", "professional", "sport")
    for kind in untouched_kinds:
        assert DEFAULT_STYLING_RULES_BY_KIND[kind].preferred_accessory_categories is None
