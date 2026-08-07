"""Tests for backend/services/engine_v2_colour.py (SS-038)."""

from __future__ import annotations

from services.engine_v2_colour import (
    hex_to_hsv,
    hue_distance_score,
    is_near_white,
    item_is_hard_excluded_white,
    pairwise_colour_harmony,
)
from services.styling_rules_types import WardrobeItemInput


def _item(id: str, color: str | None) -> WardrobeItemInput:
    return WardrobeItemInput(id=id, category="western_top", color_primary=color)


# ---------------------------------------------------------------------------
# pairwise_colour_harmony -- all-pairs, not star-topology
# ---------------------------------------------------------------------------


def test_pairwise_colour_harmony_scores_all_pairs_not_just_vs_item_zero() -> None:
    """A 3-item candidate where item[0] clashes with item[1] (60-150deg
    "clashing midrange") but item[1]/item[2] harmonize (<=30deg analogous)
    must differ from the old star-topology result (which only ever compared
    everything to item[0])."""
    # Red (#FF0000, hue 0deg), Green (#00FF00, hue 120deg -- ~120deg from red,
    # clashing midrange), a second green-ish (#22FF00, hue ~107deg -- close
    # to item[1], analogous).
    red = "#FF0000"
    green = "#00FF00"
    near_green = "#22FF00"

    all_pairs = pairwise_colour_harmony(
        [_item("a", red), _item("b", green), _item("c", near_green)]
    )

    # Old star-topology would have been mean([score(red,green), score(red,near_green)]) --
    # it never considered the green/near_green pair at all.
    old_star_mean = (hue_distance_score(red, green) + hue_distance_score(red, near_green)) / 2
    assert all_pairs != old_star_mean

    expected = (
        hue_distance_score(red, green)
        + hue_distance_score(red, near_green)
        + hue_distance_score(green, near_green)
    ) / 3
    assert abs(all_pairs - expected) < 1e-9


def test_pairwise_colour_harmony_fewer_than_two_colours_is_neutral() -> None:
    assert pairwise_colour_harmony([_item("a", "#FF0000")]) == 1.0
    assert pairwise_colour_harmony([]) == 1.0
    assert pairwise_colour_harmony([_item("a", None), _item("b", None)]) == 1.0


def test_pairwise_colour_harmony_order_independent() -> None:
    items_a = [_item("a", "#FF0000"), _item("b", "#00FF00"), _item("c", "#0000FF")]
    items_b = list(reversed(items_a))
    assert pairwise_colour_harmony(items_a) == pairwise_colour_harmony(items_b)


# ---------------------------------------------------------------------------
# hue_distance_score's 0.75 fallback -- deliberately unchanged
# ---------------------------------------------------------------------------


def test_hue_distance_score_unparsable_fallback_is_still_0_75() -> None:
    assert hue_distance_score("not-a-colour", "#FF0000") == 0.75
    assert hue_distance_score("#FF0000", "white-ish-name") == 0.75
    assert hue_distance_score("not-a-colour", "also-bad") == 0.75


def test_hue_distance_score_neutral_saturation_returns_1() -> None:
    # Pure grey (#808080) has saturation 0 -- neutral, harmonizes with anything.
    assert hue_distance_score("#808080", "#FF0000") == 1.0


def test_hue_distance_score_buckets() -> None:
    red = "#FF0000"  # hue 0
    analogous = "#FF3300"  # hue ~12deg -> <=30 -> 0.9
    assert hue_distance_score(red, analogous) == 0.9


# ---------------------------------------------------------------------------
# hex_to_hsv
# ---------------------------------------------------------------------------


def test_hex_to_hsv_parses_3_and_6_digit_hex() -> None:
    assert hex_to_hsv("#FFF") is not None
    assert hex_to_hsv("#FFFFFF") is not None
    assert hex_to_hsv("#FFF") == hex_to_hsv("#FFFFFF")


def test_hex_to_hsv_returns_none_for_unparsable() -> None:
    assert hex_to_hsv("not-a-colour") is None
    assert hex_to_hsv("#12345") is None
    assert hex_to_hsv("#GGGGGG") is None


# ---------------------------------------------------------------------------
# is_near_white / item_is_hard_excluded_white -- parity with the old
# styling_rules_engine private functions, now parameterized on thresholds.
# ---------------------------------------------------------------------------

_OLD_VALUE_THRESHOLD = 0.92
_OLD_SATURATION_THRESHOLD = 0.12


def test_is_near_white_matches_old_fixed_thresholds() -> None:
    # Same fixtures styling_rules_engine's old _is_near_white was tested with.
    assert (
        is_near_white(
            "#FFFFFF",
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is True
    )
    assert (
        is_near_white(
            "#8B0000",
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is False
    )
    assert (
        is_near_white(
            "not-a-colour",
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is False
    )


def test_item_is_hard_excluded_white_matches_old_behaviour() -> None:
    assert (
        item_is_hard_excluded_white(
            _item("i1", "#FFFFFF"),
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is True
    )
    assert (
        item_is_hard_excluded_white(
            _item("i2", "#8B0000"),
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is False
    )
    # Fail-closed: unparsable colour is excluded.
    assert (
        item_is_hard_excluded_white(
            _item("i3", "white"),
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is True
    )
    assert (
        item_is_hard_excluded_white(
            _item("i4", None),
            value_threshold=_OLD_VALUE_THRESHOLD,
            saturation_threshold=_OLD_SATURATION_THRESHOLD,
        )
        is False
    )


def test_narrowed_threshold_excludes_fewer_items() -> None:
    """A cream colour that IS near-white under the default 0.92/0.12
    threshold is NOT near-white under a much stricter (narrower) threshold
    -- proves the parameterization actually changes behaviour."""
    cream = "#FDF6E3"  # a warm off-white/cream
    hsv = hex_to_hsv(cream)
    assert hsv is not None
    _, sat, val = hsv

    default_result = is_near_white(cream, value_threshold=0.92, saturation_threshold=0.12)
    strict_result = is_near_white(
        cream, value_threshold=max(val + 0.01, 0.999), saturation_threshold=max(sat - 0.01, 0.0)
    )
    assert default_result is True
    assert strict_result is False
