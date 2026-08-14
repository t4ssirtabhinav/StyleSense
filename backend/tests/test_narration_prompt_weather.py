"""Tests for ai/adapters/styling_prompt.py's SS-022 weather threading, and
the BL-130-adjacent regression pin: render_candidate_for_prompt's
per-candidate output must be UNCHANGED by this ticket -- the weather text
must never land inside a candidate dict, only the prompt envelope."""

from __future__ import annotations

from ai.adapters.styling_prompt import build_narration_prompt
from ai.ports.interfaces import StylePreferencesInput
from services.styling_rules_engine import render_candidate_for_prompt
from services.styling_rules_types import RuleScore, ScoredCandidate

_WEATHER_CLEAR = {
    "city": "Mumbai",
    "temp_c": 28.4,
    "condition": "partly_cloudy",
    "humidity": 71,
    "is_heavy_rain": False,
    "observed_at": "2026-08-14T13:00",
}

_WEATHER_HEAVY_RAIN = {
    "city": "Mumbai",
    "temp_c": 26.0,
    "condition": "heavy_rain",
    "humidity": 92,
    "is_heavy_rain": True,
    "observed_at": "2026-08-14T13:00",
}


def _candidates() -> list[dict[str, object]]:
    return [
        {
            "items": [{"id": "a", "category": "western_top"}],
            "score": 0.8,
            "explanation": "matches well",
            "gap_flags": [],
            "outfit_fingerprint": "fp1",
        }
    ]


def test_weather_none_omits_the_block_entirely() -> None:
    prompt = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=None
    )
    assert "Current weather" not in prompt


def test_weather_present_includes_temp_condition_humidity() -> None:
    prompt = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=_WEATHER_CLEAR
    )
    assert "28" in prompt
    assert "partly cloudy" in prompt
    assert "71%" in prompt


def test_heavy_rain_adds_the_already_removed_instruction() -> None:
    prompt = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=_WEATHER_HEAVY_RAIN
    )
    assert "already been" in prompt.lower()


def test_non_heavy_rain_omits_the_already_removed_instruction() -> None:
    prompt = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=_WEATHER_CLEAR
    )
    assert "already been" not in prompt.lower()


def test_weather_present_adds_the_two_standing_instruction_lines() -> None:
    with_weather = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=_WEATHER_CLEAR
    )
    without_weather = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=None
    )
    assert "Take the weather into account" in with_weather
    assert "Do NOT quote a specific temperature" in with_weather
    assert "Take the weather into account" not in without_weather


def test_malformed_weather_dict_never_breaks_the_prompt() -> None:
    prompt = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather={"nonsense": "value"}
    )
    assert "office" in prompt  # still a valid prompt, weather block just omitted
    assert "Current weather" not in prompt


def test_weather_block_under_200_chars() -> None:
    """BL-130-adjacent: the new weather block must stay well within a small
    fixed bound."""
    prompt_with_weather = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=_WEATHER_HEAVY_RAIN
    )
    prompt_without_weather = build_narration_prompt(
        _candidates(), "office", StylePreferencesInput(), 5, weather=None
    )
    added_chars = len(prompt_with_weather) - len(prompt_without_weather)
    assert added_chars < 500  # instructions + block combined, generous bound
    # The weather block text itself (rendered by render_weather_for_prompt)
    # is separately pinned under 200 chars in test_weather_rules.py.


def test_render_candidate_for_prompt_output_unchanged_by_this_ticket() -> None:
    """BL-130 regression pin: the weather text must never land inside a
    candidate dict -- render_candidate_for_prompt's per-candidate output is
    byte-for-byte identical regardless of any weather concept existing."""
    candidate = ScoredCandidate(
        item_ids=["a", "b"],
        category_labels={"a": "Top", "b": "Bottom"},
        total_score=0.8,
        rule_scores=[
            RuleScore(rule="formality_fit", score=0.9, explanation="great formality match"),
            RuleScore(rule="colour_harmony", score=0.7, explanation="colours work well together"),
        ],
        gap_flags=[],
    )
    rendered = render_candidate_for_prompt(candidate)
    assert rendered == {
        "items": [
            {"id": "a", "category": "Top"},
            {"id": "b", "category": "Bottom"},
        ],
        "score": 0.8,
        "explanation": "great formality match; colours work well together",
        "gap_flags": [],
    }
    assert "weather" not in rendered
