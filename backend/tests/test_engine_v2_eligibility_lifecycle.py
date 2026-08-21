"""Tests for backend/services/engine_v2_eligibility.py's SS-040 lifecycle
exclusion (do_not_style/is_archived) -- the AC's "asserted by a test"."""

from __future__ import annotations

from services.app_config_specs import NearWhiteThresholdConfig
from services.engine_v2_eligibility import filter_eligible, resolve_styling_rules
from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput
from services.weather_rules import WeatherContext


def _item(
    id: str,
    *,
    category: str | None = "ethnic_saree",
    color: str | None = "#8B0000",
    fabric: str | None = None,
    do_not_style: bool = False,
    is_archived: bool = False,
) -> WardrobeItemInput:
    return WardrobeItemInput(
        id=id,
        category=category,  # type: ignore[arg-type]
        color_primary=color,
        fabric=fabric,
        do_not_style=do_not_style,
        is_archived=is_archived,
    )


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


def _near_white() -> NearWhiteThresholdConfig:
    return NearWhiteThresholdConfig()


def _heavy_rain_weather() -> WeatherContext:
    return WeatherContext(
        city="Mumbai",
        temp_c=26.0,
        condition="heavy_rain",
        humidity=90,
        is_heavy_rain=True,
        observed_at="2026-08-14T10:45",
    )


def test_do_not_style_item_is_excluded_from_eligible_pool() -> None:
    wardrobe = [
        _item("a", do_not_style=True),
        _item("b"),
        _item("c"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=_near_white())
    eligible_ids = {item.id for item in result.eligible_items}
    assert "a" not in eligible_ids
    assert eligible_ids == {"b", "c"}


def test_is_archived_item_is_excluded_from_eligible_pool() -> None:
    wardrobe = [
        _item("a", is_archived=True),
        _item("b"),
        _item("c"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=_near_white())
    eligible_ids = {item.id for item in result.eligible_items}
    assert "a" not in eligible_ids
    assert eligible_ids == {"b", "c"}


def test_item_with_both_flags_is_counted_once() -> None:
    wardrobe = [_item("a", do_not_style=True, is_archived=True)]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=_near_white())
    assert result.eligible_items == []
    assert result.excluded_lifecycle == 1


def test_excluded_lifecycle_counts_distinct_items() -> None:
    wardrobe = [
        _item("a", do_not_style=True),
        _item("b", is_archived=True),
        _item("c"),
        _item("d"),
        _item("e"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=_near_white())
    assert result.excluded_lifecycle == 2
    assert len(result.eligible_items) == 3


def test_archived_item_missing_category_is_not_also_counted_as_missing() -> None:
    """Ordering decision (design §"The exclusion itself", point 1), made
    falsifiable: an archived+untagged item must count ONLY in
    excluded_lifecycle, never also in excluded_missing_color_or_category."""
    wardrobe = [_item("a", is_archived=True, category=None)]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(wardrobe, occasion, rules, near_white_thresholds=_near_white())
    assert result.excluded_lifecycle == 1
    assert result.excluded_missing_color_or_category == 0


def test_lifecycle_exclusions_are_not_relaxed_when_pool_empties_under_weather() -> None:
    """Every non-flagged item is white/silk under heavy rain so the
    relax-if-empty guardrail fires; the do_not_style item must still be
    absent from eligible_items even though the pool would otherwise be
    empty. The user's explicit instruction beats the engine's weather
    inference."""
    wardrobe = [
        _item("banned", do_not_style=True, color="#8B0000", fabric="cotton"),
        _item("white_silk", color="#FFFFFF", fabric="silk"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(
        wardrobe,
        occasion,
        rules,
        near_white_thresholds=_near_white(),
        weather=_heavy_rain_weather(),
    )
    eligible_ids = {item.id for item in result.eligible_items}
    assert "banned" not in eligible_ids
    assert eligible_ids == {"white_silk"}
    assert result.weather_exclusions_relaxed is True


def test_default_wardrobe_item_input_is_stylable() -> None:
    item = WardrobeItemInput(id="x", category="ethnic_saree", color_primary="#8B0000")
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible([item], occasion, rules, near_white_thresholds=_near_white())
    assert {i.id for i in result.eligible_items} == {"x"}
    assert result.excluded_lifecycle == 0


def test_row_dict_without_lifecycle_keys_validates() -> None:
    item = WardrobeItemInput.model_validate(
        {"id": "x", "category": "ethnic_saree", "color_primary": "#8B0000"}
    )
    assert item.do_not_style is False
    assert item.is_archived is False
    assert item.custom_tags == []


def test_custom_tags_are_stored_verbatim() -> None:
    raw = ["office", "Office", " office "]
    item = WardrobeItemInput(
        id="x",
        category="ethnic_saree",
        color_primary="#8B0000",
        custom_tags=raw,
    )
    assert item.custom_tags == raw
