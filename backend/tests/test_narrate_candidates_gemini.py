"""Tests for GeminiStylingAdapter.narrate_candidates (SS-020), against a
mocked ``google-genai`` client -- mirrors test_gemini_styling_adapter.py's
own fake-client shape exactly, no real network/API-key usage."""

from __future__ import annotations

import json
from typing import Any

from google.genai import errors

from ai.adapters.gemini_styling_adapter import GeminiStylingAdapter
from ai.adapters.styling_call import (
    ProviderParseError,
    ProviderPermanentError,
    ProviderQuotaExhaustedError,
    ProviderTransientError,
)
from ai.ports.interfaces import StylePreferencesInput

VALID_NARRATIONS = {
    "narrations": [
        {"outfit_fingerprint": "fp1", "rationale": "a great pick for the office", "rank": None}
    ]
}


class _FakeUsage:
    def __init__(self, prompt_token_count: int, candidates_token_count: int) -> None:
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count


class _FakeResponse:
    def __init__(self, text: str | None, usage: _FakeUsage | None = None) -> None:
        self.text = text
        self.usage_metadata = usage or _FakeUsage(100, 50)


class _FakeModels:
    def __init__(self, side_effects: list[Any]) -> None:
        self._side_effects = list(side_effects)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, *, model: str, contents: Any, config: Any) -> _FakeResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        effect = self._side_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


class _FakeAio:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


class _FakeClient:
    def __init__(self, side_effects: list[Any]) -> None:
        self.models = _FakeModels(side_effects)
        self.aio = _FakeAio(self.models)


def _valid_response() -> _FakeResponse:
    return _FakeResponse(json.dumps(VALID_NARRATIONS))


def _candidate(fingerprint: str = "fp1") -> dict[str, Any]:
    return {
        "items": [{"id": "a", "category": "western_top"}],
        "score": 0.8,
        "explanation": "matches well",
        "gap_flags": [],
        "outfit_fingerprint": fingerprint,
    }


async def test_never_invents_a_fingerprint_outside_input_candidates() -> None:
    client = _FakeClient([_valid_response()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)
    result = await adapter.narrate_candidates(
        [_candidate("fp1")],
        occasion="office",
        preferences=StylePreferencesInput(),
        max_suggestions=5,
    )
    assert all(n.outfit_fingerprint == "fp1" for n in result.narrations)
    assert result.source == "gemini"


async def test_server_error_maps_to_provider_transient_error() -> None:
    client = _FakeClient(
        [errors.ServerError(503, {"message": "unavailable", "status": "UNAVAILABLE"})]
    )
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()],
            occasion="office",
            preferences=StylePreferencesInput(),
            max_suggestions=5,
        )
        raise AssertionError("expected ProviderTransientError")
    except ProviderTransientError:
        pass


async def test_client_error_429_maps_to_quota_exhausted() -> None:
    client = _FakeClient(
        [errors.ClientError(429, {"message": "too many", "status": "RESOURCE_EXHAUSTED"})]
    )
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()],
            occasion="office",
            preferences=StylePreferencesInput(),
            max_suggestions=5,
        )
        raise AssertionError("expected ProviderQuotaExhaustedError")
    except ProviderQuotaExhaustedError:
        pass


async def test_client_error_404_maps_to_permanent_error() -> None:
    client = _FakeClient([errors.ClientError(404, {"message": "not found", "status": "NOT_FOUND"})])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()],
            occasion="office",
            preferences=StylePreferencesInput(),
            max_suggestions=5,
        )
        raise AssertionError("expected ProviderPermanentError")
    except ProviderPermanentError:
        pass


async def test_empty_response_maps_to_parse_error() -> None:
    client = _FakeClient([_FakeResponse(None)])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()],
            occasion="office",
            preferences=StylePreferencesInput(),
            max_suggestions=5,
        )
        raise AssertionError("expected ProviderParseError")
    except ProviderParseError:
        pass


async def test_weather_none_default_and_populated_dict_both_produce_unchanged_shape() -> None:
    client = _FakeClient([_valid_response(), _valid_response()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)

    result_no_weather = await adapter.narrate_candidates(
        [_candidate("fp1")],
        occasion="office",
        preferences=StylePreferencesInput(),
        max_suggestions=5,
    )
    weather = {
        "city": "Mumbai",
        "temp_c": 28.0,
        "condition": "clear",
        "humidity": 60,
        "is_heavy_rain": False,
        "observed_at": "2026-08-14T13:00",
    }
    result_with_weather = await adapter.narrate_candidates(
        [_candidate("fp1")],
        occasion="office",
        preferences=StylePreferencesInput(),
        max_suggestions=5,
        weather=weather,
    )

    assert result_no_weather.source == "gemini"
    assert result_with_weather.source == "gemini"
    assert [n.outfit_fingerprint for n in result_no_weather.narrations] == ["fp1"]
    assert [n.outfit_fingerprint for n in result_with_weather.narrations] == ["fp1"]

    # The weather block actually reached the rendered prompt text.
    second_call_prompt = client.models.calls[1]["contents"][0]
    assert "28" in second_call_prompt
    assert "clear" in second_call_prompt


async def test_malformed_json_maps_to_parse_error() -> None:
    client = _FakeClient([_FakeResponse("not json")])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()],
            occasion="office",
            preferences=StylePreferencesInput(),
            max_suggestions=5,
        )
        raise AssertionError("expected ProviderParseError")
    except ProviderParseError:
        pass
