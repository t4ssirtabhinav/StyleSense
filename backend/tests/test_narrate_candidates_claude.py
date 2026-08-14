"""Tests for ClaudeStylingAdapter.narrate_candidates (SS-020), against a
mocked ``anthropic`` client -- mirrors test_claude_styling_adapter.py's own
fake-client shape exactly, no real network/API-key usage."""

from __future__ import annotations

from typing import Any

import anthropic
import httpx

from ai.adapters.claude_styling_adapter import ClaudeStylingAdapter
from ai.adapters.styling_call import (
    ProviderParseError,
    ProviderPermanentError,
    ProviderQuotaExhaustedError,
    ProviderTransientError,
)
from ai.ports.interfaces import StylePreferencesInput

VALID_NARRATION_TOOL_INPUT = {
    "narrations": [
        {"outfit_fingerprint": "fp1", "rationale": "high-stakes-quality narration", "rank": None}
    ]
}


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeToolUseBlock:
    def __init__(self, input_dict: dict[str, Any]) -> None:
        self.type = "tool_use"
        self.input = input_dict


class _FakeMessage:
    def __init__(self, content: list[Any], usage: _FakeUsage | None = None) -> None:
        self.content = content
        self.usage = usage or _FakeUsage(200, 80)


class _FakeMessages:
    def __init__(self, side_effects: list[Any]) -> None:
        self._side_effects = list(side_effects)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        effect = self._side_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


class _FakeClient:
    def __init__(self, side_effects: list[Any]) -> None:
        self.messages = _FakeMessages(side_effects)


def _valid_message() -> _FakeMessage:
    return _FakeMessage([_FakeToolUseBlock(VALID_NARRATION_TOOL_INPUT)])


def _fake_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(
        status_code, request=request, json={"error": {"type": "x", "message": "x"}}
    )


def _rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError("rate limited", response=_fake_response(429), body=None)


def _server_error() -> anthropic.InternalServerError:
    return anthropic.InternalServerError("server error", response=_fake_response(500), body=None)


def _not_found_error() -> anthropic.NotFoundError:
    return anthropic.NotFoundError("model not found", response=_fake_response(404), body=None)


def _candidate(fingerprint: str = "fp1") -> dict[str, Any]:
    return {
        "items": [{"id": "a", "category": "ethnic_saree"}],
        "score": 0.9,
        "explanation": "matches well",
        "gap_flags": [],
        "outfit_fingerprint": fingerprint,
    }


async def test_never_invents_a_fingerprint_outside_input_candidates() -> None:
    client = _FakeClient([_valid_message()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=client)
    result = await adapter.narrate_candidates(
        [_candidate("fp1")], occasion="puja", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert all(n.outfit_fingerprint == "fp1" for n in result.narrations)
    assert result.source == "claude"


async def test_rate_limit_error_maps_to_quota_exhausted() -> None:
    client = _FakeClient([_rate_limit_error()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()], occasion="puja", preferences=StylePreferencesInput(), max_suggestions=5
        )
        raise AssertionError("expected ProviderQuotaExhaustedError")
    except ProviderQuotaExhaustedError:
        pass


async def test_server_error_maps_to_provider_transient_error() -> None:
    client = _FakeClient([_server_error()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()], occasion="puja", preferences=StylePreferencesInput(), max_suggestions=5
        )
        raise AssertionError("expected ProviderTransientError")
    except ProviderTransientError:
        pass


async def test_not_found_error_maps_to_permanent_error() -> None:
    client = _FakeClient([_not_found_error()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()], occasion="puja", preferences=StylePreferencesInput(), max_suggestions=5
        )
        raise AssertionError("expected ProviderPermanentError")
    except ProviderPermanentError:
        pass


async def test_weather_none_default_and_populated_dict_both_produce_unchanged_shape() -> None:
    client = _FakeClient([_valid_message(), _valid_message()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=client)

    result_no_weather = await adapter.narrate_candidates(
        [_candidate("fp1")], occasion="puja", preferences=StylePreferencesInput(), max_suggestions=5
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
        occasion="puja",
        preferences=StylePreferencesInput(),
        max_suggestions=5,
        weather=weather,
    )

    assert result_no_weather.source == "claude"
    assert result_with_weather.source == "claude"
    assert [n.outfit_fingerprint for n in result_no_weather.narrations] == ["fp1"]
    assert [n.outfit_fingerprint for n in result_with_weather.narrations] == ["fp1"]

    second_call_prompt = client.messages.calls[1]["messages"][0]["content"]
    assert "28" in second_call_prompt
    assert "clear" in second_call_prompt


async def test_no_tool_use_block_maps_to_parse_error() -> None:
    client = _FakeClient([_FakeMessage([])])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=client)
    try:
        await adapter.narrate_candidates(
            [_candidate()], occasion="puja", preferences=StylePreferencesInput(), max_suggestions=5
        )
        raise AssertionError("expected ProviderParseError")
    except ProviderParseError:
        pass
