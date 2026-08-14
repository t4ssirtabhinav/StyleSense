"""Tests for backend/services/weather_rules.py (SS-022) -- the AC-3 proof,
all pure."""

from __future__ import annotations

import pytest

from services.weather_rules import (
    WeatherContext,
    condition_for_wmo_code,
    is_heavy_rain,
    render_weather_for_prompt,
    weather_cache_bucket,
    weather_excluded_color_families,
    weather_excluded_fabrics,
)

_WMO_TABLE: dict[int | None, str] = {
    0: "clear",
    1: "partly_cloudy",
    2: "partly_cloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "drizzle",
    57: "drizzle",
    61: "rain",
    63: "rain",
    66: "rain",
    67: "rain",
    80: "rain",
    81: "rain",
    65: "heavy_rain",
    82: "heavy_rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}


@pytest.mark.parametrize("code,expected", list(_WMO_TABLE.items()))
def test_condition_for_wmo_code_table(code: int, expected: str) -> None:
    assert condition_for_wmo_code(code) == expected


def test_condition_for_wmo_code_unknown_falls_back_to_cloudy() -> None:
    assert condition_for_wmo_code(999) == "cloudy"


def test_condition_for_wmo_code_none_falls_back_to_cloudy() -> None:
    assert condition_for_wmo_code(None) == "cloudy"


@pytest.mark.parametrize("code", [65, 82, 95, 96, 99])
def test_is_heavy_rain_true_for_heavy_rain_codes(code: int) -> None:
    assert is_heavy_rain(weather_code=code, precipitation_mm=0.0, precip_threshold_mm_per_hour=7.6)


def test_is_heavy_rain_true_for_precipitation_at_default_threshold() -> None:
    assert is_heavy_rain(weather_code=61, precipitation_mm=8.0, precip_threshold_mm_per_hour=7.6)


def test_is_heavy_rain_false_for_light_rain_below_threshold() -> None:
    assert not is_heavy_rain(
        weather_code=61, precipitation_mm=1.0, precip_threshold_mm_per_hour=7.6
    )


def test_is_heavy_rain_honours_non_default_threshold() -> None:
    """Proves the app_config wiring is real, not decorative."""
    assert is_heavy_rain(weather_code=61, precipitation_mm=2.0, precip_threshold_mm_per_hour=1.5)
    assert not is_heavy_rain(
        weather_code=61, precipitation_mm=1.0, precip_threshold_mm_per_hour=1.5
    )


def _weather(
    *, condition: str = "clear", is_heavy: bool = False, temp_c: float = 28.0, humidity: int = 60
) -> WeatherContext:
    return WeatherContext(
        city="Mumbai",
        temp_c=temp_c,
        condition=condition,  # type: ignore[arg-type]
        humidity=humidity,
        is_heavy_rain=is_heavy,
        observed_at="2026-08-14T10:45",
    )


def test_weather_excluded_color_families_only_heavy_rain() -> None:
    assert weather_excluded_color_families(_weather(condition="heavy_rain", is_heavy=True)) == {
        "white"
    }
    assert (
        weather_excluded_color_families(_weather(condition="rain", is_heavy=False)) == frozenset()
    )
    assert (
        weather_excluded_color_families(_weather(condition="drizzle", is_heavy=False))
        == frozenset()
    )
    assert (
        weather_excluded_color_families(_weather(condition="thunderstorm", is_heavy=False))
        == frozenset()
    )
    assert (
        weather_excluded_color_families(_weather(condition="clear", is_heavy=False)) == frozenset()
    )


def test_weather_excluded_fabrics_only_heavy_rain() -> None:
    assert weather_excluded_fabrics(_weather(condition="heavy_rain", is_heavy=True)) == {"silk"}
    assert weather_excluded_fabrics(_weather(condition="rain", is_heavy=False)) == frozenset()


def test_weather_cache_bucket_none() -> None:
    assert weather_cache_bucket(None) == "none"


def test_weather_cache_bucket_heavy_rain() -> None:
    assert (
        weather_cache_bucket(_weather(condition="heavy_rain", is_heavy=True, temp_c=25.0))
        == "heavy_rain"
    )


def test_weather_cache_bucket_bands_coarsen_within_five_degrees() -> None:
    assert weather_cache_bucket(_weather(condition="clear", temp_c=28.0)) == "dry:30"
    assert weather_cache_bucket(_weather(condition="clear", temp_c=29.0)) == "dry:30"


def test_weather_cache_bucket_bands_differ_across_five_degrees() -> None:
    assert weather_cache_bucket(_weather(condition="clear", temp_c=22.0)) == "dry:20"


def test_weather_cache_bucket_condition_class_flips_bucket_at_same_temperature() -> None:
    assert weather_cache_bucket(_weather(condition="rain", temp_c=28.0)) == "wet:30"
    assert weather_cache_bucket(_weather(condition="clear", temp_c=28.0)) == "dry:30"


def test_render_weather_for_prompt_includes_temp_condition_humidity() -> None:
    text = render_weather_for_prompt(_weather(condition="partly_cloudy", temp_c=28.4, humidity=71))
    assert "28" in text
    assert "partly cloudy" in text
    assert "71%" in text


def test_render_weather_for_prompt_heavy_rain_line_only_when_heavy() -> None:
    heavy = render_weather_for_prompt(_weather(condition="heavy_rain", is_heavy=True))
    not_heavy = render_weather_for_prompt(_weather(condition="clear", is_heavy=False))
    assert "already been" in heavy.lower()
    assert "already been" not in not_heavy.lower()


def test_render_weather_for_prompt_under_200_chars() -> None:
    text = render_weather_for_prompt(_weather(condition="heavy_rain", is_heavy=True, humidity=95))
    assert len(text) < 200
