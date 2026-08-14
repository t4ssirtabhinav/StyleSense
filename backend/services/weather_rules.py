"""SS-022 -- every weather -> behaviour decision in this ticket, pure, no
I/O. ``WeatherContext``, the WMO code -> condition mapping, the heavy-rain
predicate, the heavy-rain exclusion sets, the narration cache bucket, and
the narration prompt's weather block all live here and nowhere else (design
§3/§4/§5).

WMO code table ``[VERIFIED 2026-08-14, https://open-meteo.com/en/docs's own
published "WMO Weather interpretation codes (WW)" table]`` -- see
``docs/worklog/SS-022.md``'s Developer entry for the fetched table.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

__all__ = [
    "WeatherCondition",
    "WeatherContext",
    "WMO_CODE_TO_CONDITION",
    "condition_for_wmo_code",
    "is_heavy_rain",
    "weather_excluded_color_families",
    "weather_excluded_fabrics",
    "weather_cache_bucket",
    "render_weather_for_prompt",
]

WeatherCondition = Literal[
    "clear",
    "partly_cloudy",
    "cloudy",
    "fog",
    "drizzle",
    "rain",
    "heavy_rain",
    "thunderstorm",
    "snow",
]

_CONDITION_LABELS: dict[WeatherCondition, str] = {
    "clear": "clear",
    "partly_cloudy": "partly cloudy",
    "cloudy": "cloudy",
    "fog": "foggy",
    "drizzle": "drizzly",
    "rain": "rainy",
    "heavy_rain": "heavy rain",
    "thunderstorm": "thunderstorms",
    "snow": "snow",
}

# WMO code -> condition, [VERIFIED 2026-08-14] against Open-Meteo's own
# published table (see module docstring). "anything else / missing" ->
# "cloudy" (neutral fallback, never raise on an unknown code) -- handled by
# condition_for_wmo_code's default, not listed here.
WMO_CODE_TO_CONDITION: dict[int, WeatherCondition] = {
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

# Heavy rain, violent showers, all thunderstorm -- the single decision AC #3
# hangs on.
_HEAVY_RAIN_CODES: frozenset[int] = frozenset({65, 82, 95, 96, 99})

WEATHER_EXCLUDED_COLOR_FAMILIES: dict[str, frozenset[str]] = {
    "heavy_rain": frozenset({"white"}),
}
WEATHER_EXCLUDED_FABRICS: dict[str, frozenset[str]] = {
    "heavy_rain": frozenset({"silk"}),
}


class WeatherContext(BaseModel):
    """The derived, in-app shape -- what everything downstream of
    ``WeatherService.resolve_for_user`` actually consumes."""

    city: str  # display name, e.g. "Mumbai"
    temp_c: float
    condition: WeatherCondition
    humidity: int
    is_heavy_rain: bool
    observed_at: str


def condition_for_wmo_code(code: int | None) -> WeatherCondition:
    """``None``/missing/unknown code -> ``"cloudy"`` (neutral fallback,
    never raises)."""
    if code is None:
        return "cloudy"
    return WMO_CODE_TO_CONDITION.get(code, "cloudy")


def is_heavy_rain(
    *, weather_code: int | None, precipitation_mm: float, precip_threshold_mm_per_hour: float
) -> bool:
    """The single decision AC #3 hangs on: a heavy-rain/violent-shower/
    thunderstorm WMO code, OR a precipitation rate at/above the (app_config-
    tunable) threshold."""
    if weather_code is not None and weather_code in _HEAVY_RAIN_CODES:
        return True
    return precipitation_mm >= precip_threshold_mm_per_hour


def _condition_class(is_heavy: bool) -> str:
    return "heavy_rain" if is_heavy else "other"


def weather_excluded_color_families(weather: WeatherContext) -> frozenset[str]:
    return WEATHER_EXCLUDED_COLOR_FAMILIES.get(_condition_class(weather.is_heavy_rain), frozenset())


def weather_excluded_fabrics(weather: WeatherContext) -> frozenset[str]:
    return WEATHER_EXCLUDED_FABRICS.get(_condition_class(weather.is_heavy_rain), frozenset())


def weather_cache_bucket(weather: WeatherContext | None) -> str:
    """Coarse on purpose (design §5) -- 3 condition classes x ~8 realistic
    Indian temperature bands, so cross-user narration-cache sharing
    survives. Humidity is deliberately excluded."""
    if weather is None:
        return "none"
    if weather.is_heavy_rain:
        return "heavy_rain"
    wet = weather.condition in {"drizzle", "rain", "thunderstorm", "snow"}
    band = int(round(weather.temp_c / 5.0) * 5)
    return f"{'wet' if wet else 'dry'}:{band}"


def render_weather_for_prompt(weather: WeatherContext) -> str:
    """Compact block appended after the narration prompt's preferences
    block (design §4). Under 200 chars (``BL-130``-adjacent test pin)."""
    condition_label = _CONDITION_LABELS[weather.condition]
    lines = [
        f"Current weather where the user is: {round(weather.temp_c)}°C, "
        f"{condition_label}, humidity {weather.humidity}%."
    ]
    if weather.is_heavy_rain:
        lines.append(
            "It is raining heavily -- white and silk items have ALREADY been "
            "removed from the candidates below; do not mention their absence."
        )
    return "\n".join(lines)
