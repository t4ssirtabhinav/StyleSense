"""Tests for backend/ai/adapters/claude_styling_adapter.py (SS-028 design
§11), against a mocked ``anthropic`` client -- no real network/API-key
usage in this suite. A real live call was made separately, once, during the
Developer phase to verify the call shape/model ID (tool-use structured
output, ``claude-sonnet-5``) -- see the adapter's own module docstring,
services/ai_routing_specs.py, and docs/worklog/SS-028.md.
"""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic
import httpx
import pytest

from ai.adapters.claude_styling_adapter import ClaudeStylingAdapter
from ai.adapters.styling_call import (
    ProviderParseError,
    ProviderPermanentError,
    ProviderQuotaExhaustedError,
    ProviderTimeoutError,
    ProviderTransientError,
)
from ai.ports.interfaces import StylePreferencesInput

VALID_TOOL_INPUT = {
    "suggestions": [
        {
            "item_category": "ethnic_saree",
            "label": "Silk Blend Saree",
            "occasion": "puja",
            "rationale": "high-stakes-quality suggestion",
        }
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


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


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
        if callable(effect):
            return await effect()
        return effect


class _FakeClient:
    def __init__(self, side_effects: list[Any]) -> None:
        self.messages = _FakeMessages(side_effects)


def _valid_message(input_tokens: int = 200, output_tokens: int = 80) -> _FakeMessage:
    return _FakeMessage(
        [_FakeToolUseBlock(VALID_TOOL_INPUT)], _FakeUsage(input_tokens, output_tokens)
    )


def _fake_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code, request=request, json={"error": {"type": "x", "message": "x"}})


def _rate_limit_error() -> anthropic.RateLimitError:
    response = _fake_response(429)
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def _server_error() -> anthropic.InternalServerError:
    response = _fake_response(500)
    return anthropic.InternalServerError("server error", response=response, body=None)


def _not_found_error() -> anthropic.NotFoundError:
    response = _fake_response(404)
    return anthropic.NotFoundError("model not found", response=response, body=None)


async def test_well_formed_tool_use_succeeds_with_expected_source_and_model() -> None:
    fake_client = _FakeClient([_valid_message()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    result, metrics = await adapter.suggest_outfits_with_metrics(
        StylePreferencesInput(styles=["ethnic"])
    )

    assert result.source == "claude"
    assert metrics.provider == "claude"
    assert metrics.model == "claude-sonnet-5"
    assert metrics.tokens_in == 200
    assert metrics.tokens_out == 80
    assert len(result.suggestions) == 1


async def test_two_adapters_with_two_model_ids_call_the_sdk_with_those_exact_strings() -> None:
    fake_client_a = _FakeClient([_valid_message()])
    fake_client_b = _FakeClient([_valid_message()])
    adapter_a = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client_a)
    adapter_b = ClaudeStylingAdapter(model="claude-haiku-4-5", client=fake_client_b)

    await adapter_a.suggest_outfits(StylePreferencesInput())
    await adapter_b.suggest_outfits(StylePreferencesInput())

    assert fake_client_a.messages.calls[0]["model"] == "claude-sonnet-5"
    assert fake_client_b.messages.calls[0]["model"] == "claude-haiku-4-5"


async def test_missing_tool_use_block_raises_provider_parse_error() -> None:
    fake_client = _FakeClient([_FakeMessage([_FakeTextBlock("I decided not to use the tool.")])])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    with pytest.raises(ProviderParseError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_malformed_tool_input_raises_provider_parse_error() -> None:
    fake_client = _FakeClient([_FakeMessage([_FakeToolUseBlock({"not": "the right shape"})])])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    with pytest.raises(ProviderParseError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_server_error_raises_provider_transient_error() -> None:
    fake_client = _FakeClient([_server_error()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    with pytest.raises(ProviderTransientError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_rate_limit_error_raises_provider_quota_exhausted_error() -> None:
    fake_client = _FakeClient([_rate_limit_error()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    with pytest.raises(ProviderQuotaExhaustedError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_not_found_error_raises_provider_permanent_error() -> None:
    fake_client = _FakeClient([_not_found_error()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    with pytest.raises(ProviderPermanentError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_hanging_client_raises_provider_timeout_error_within_timeout_seconds() -> None:
    async def _hang() -> _FakeMessage:
        await asyncio.sleep(10)
        return _valid_message()

    fake_client = _FakeClient([_hang])
    adapter = ClaudeStylingAdapter(
        model="claude-sonnet-5", client=fake_client, timeout_seconds=0.05
    )

    with pytest.raises(ProviderTimeoutError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_missing_api_key_raises_provider_permanent_error_not_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5")

    with pytest.raises(ProviderPermanentError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_max_suggestions_enforced_by_slicing_not_only_prompt() -> None:
    payload = {
        "suggestions": [
            {"item_category": "ethnic_kurta", "label": f"Item {i}", "rationale": "r"}
            for i in range(5)
        ]
    }
    fake_client = _FakeClient([_FakeMessage([_FakeToolUseBlock(payload)])])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    result = await adapter.suggest_outfits(StylePreferencesInput(), max_suggestions=2)

    assert len(result.suggestions) == 2


async def test_zero_suggestions_after_slicing_raises_provider_parse_error() -> None:
    fake_client = _FakeClient([_FakeMessage([_FakeToolUseBlock({"suggestions": []})])])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    with pytest.raises(ProviderParseError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_empty_preferences_does_not_raise_and_is_not_personalized() -> None:
    fake_client = _FakeClient([_valid_message()])
    adapter = ClaudeStylingAdapter(model="claude-sonnet-5", client=fake_client)

    result = await adapter.suggest_outfits(StylePreferencesInput())

    assert result.is_personalized is False
