"""Tests for backend/services/engine_v2_eligibility.py's SS-022 weather
extension -- AC #3 ("heavy rain -> no white or silk"), the acceptance
criterion itself."""

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
) -> WardrobeItemInput:
    return WardrobeItemInput(
        id=id,
        category=category,  # type: ignore[arg-type]
        color_primary=color,
        fabric=fabric,
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


def _heavy_rain_weather(*, temp_c: float = 26.0) -> WeatherContext:
    return WeatherContext(
        city="Mumbai",
        temp_c=temp_c,
        condition="heavy_rain",
        humidity=90,
        is_heavy_rain=True,
        observed_at="2026-08-14T10:45",
    )


def _light_rain_weather() -> WeatherContext:
    return WeatherContext(
        city="Mumbai",
        temp_c=27.0,
        condition="rain",
        humidity=70,
        is_heavy_rain=False,
        observed_at="2026-08-14T10:45",
    )


# ---------------------------------------------------------------------------
# AC #3 (white)
# ---------------------------------------------------------------------------


def test_heavy_rain_excludes_white_and_near_white() -> None:
    wardrobe = [
        _item("white1", color="#FFFFFF"),
        _item("ivory1", color="#FFFEF8"),
        _item("red1", color="#8B0000"),
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
    assert "white1" not in eligible_ids
    assert "ivory1" not in eligible_ids
    assert "red1" in eligible_ids


def test_same_wardrobe_with_weather_none_retains_white() -> None:
    wardrobe = [_item("white1", color="#FFFFFF"), _item("ivory1", color="#FFFEF8")]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(
        wardrobe, occasion, rules, near_white_thresholds=_near_white(), weather=None
    )
    eligible_ids = {item.id for item in result.eligible_items}
    assert "white1" in eligible_ids
    assert "ivory1" in eligible_ids


# ---------------------------------------------------------------------------
# AC #3 (silk)
# ---------------------------------------------------------------------------


def test_heavy_rain_excludes_silk_fabric() -> None:
    wardrobe = [
        _item("silk1", color="#8B0000", fabric="silk"),
        _item("cotton1", color="#8B0000", fabric="cotton"),
        _item("rayon1", color="#8B0000", fabric="rayon"),  # what art_silk normalises to
        _item("nofabric1", color="#8B0000", fabric=None),
        _item("upper_silk", color="#8B0000", fabric="SILK"),
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
    assert "silk1" not in eligible_ids
    assert "upper_silk" not in eligible_ids  # case-insensitive belt-and-braces
    assert "cotton1" in eligible_ids
    assert "rayon1" in eligible_ids  # art_silk normalises to rayon -- NOT silk, retained
    assert "nofabric1" in eligible_ids  # no fabric -- never excluded, safe direction


# ---------------------------------------------------------------------------
# Non-heavy rain excludes nothing
# ---------------------------------------------------------------------------


def test_non_heavy_rain_excludes_nothing() -> None:
    wardrobe = [
        _item("white1", color="#FFFFFF"),
        _item("silk1", color="#8B0000", fabric="silk"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(
        wardrobe,
        occasion,
        rules,
        near_white_thresholds=_near_white(),
        weather=_light_rain_weather(),
    )
    eligible_ids = {item.id for item in result.eligible_items}
    assert "white1" in eligible_ids
    assert "silk1" in eligible_ids


def test_weather_none_produces_identical_result_to_pre_ss022() -> None:
    wardrobe = [
        _item("a", color="#1E3A8A", fabric="cotton"),
        _item("b", color="#FFFFFF", fabric="silk"),
    ]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    with_weather_none = filter_eligible(
        wardrobe, occasion, rules, near_white_thresholds=_near_white(), weather=None
    )
    without_weather_kwarg = filter_eligible(
        wardrobe, occasion, rules, near_white_thresholds=_near_white()
    )
    assert with_weather_none.eligible_items == without_weather_kwarg.eligible_items
    assert (
        with_weather_none.excluded_missing_color_or_category
        == without_weather_kwarg.excluded_missing_color_or_category
    )
    assert with_weather_none.weather_exclusions_relaxed is False
    assert without_weather_kwarg.weather_exclusions_relaxed is False


# ---------------------------------------------------------------------------
# Relax-if-empty guardrail
# ---------------------------------------------------------------------------


def test_relax_if_empty_all_white_silk_wardrobe_returns_pre_weather_set() -> None:
    wardrobe = [
        _item("white_silk1", color="#FFFFFF", fabric="silk"),
        _item("white_silk2", color="#FFFEF8", fabric="silk"),
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
    assert eligible_ids == {"white_silk1", "white_silk2"}
    assert result.weather_exclusions_relaxed is True


def test_relax_if_empty_does_not_fire_when_pre_weather_already_empty() -> None:
    """The already-ineligible wardrobe case -- missing category/colour, not
    weather. The flag must mean 'we relaxed a rule,' never 'you own
    nothing.'"""
    wardrobe = [_item("no_cat", category=None, color="#FFFFFF")]
    occasion = _occasion()
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(
        wardrobe,
        occasion,
        rules,
        near_white_thresholds=_near_white(),
        weather=_heavy_rain_weather(),
    )
    assert result.eligible_items == []
    assert result.weather_exclusions_relaxed is False


# ---------------------------------------------------------------------------
# Interaction with an existing hard exclusion (wedding_guest)
# ---------------------------------------------------------------------------


def test_wedding_guest_plus_heavy_rain_excludes_white_exactly_once() -> None:
    wardrobe = [
        _item("white1", category="ethnic_saree", color="#FFFFFF"),
        _item("red1", category="ethnic_saree", color="#8B0000"),
    ]
    occasion = _occasion(key="wedding_guest", kind="ceremony", formality=9)
    rules = resolve_styling_rules(occasion)
    result = filter_eligible(
        wardrobe,
        occasion,
        rules,
        near_white_thresholds=_near_white(),
        weather=_heavy_rain_weather(),
    )
    eligible_ids = {item.id for item in result.eligible_items}
    assert "white1" not in eligible_ids
    assert "red1" in eligible_ids
    assert result.weather_exclusions_relaxed is False
