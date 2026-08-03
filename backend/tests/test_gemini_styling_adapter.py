"""Tests for backend/ai/adapters/gemini_styling_adapter.py (SS-028 design
§11), against a mocked ``google-genai`` client -- no real network/API-key
usage in this suite (a real live call was made separately, once, during the
Developer phase to verify the call shape/model IDs -- see the adapter's own
module docstring, services/ai_routing_specs.py, and docs/worklog/SS-028.md).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from google.genai import errors

from ai.adapters.gemini_styling_adapter import GeminiStylingAdapter
from ai.adapters.styling_call import (
    ProviderParseError,
    ProviderPermanentError,
    ProviderQuotaExhaustedError,
    ProviderTimeoutError,
    ProviderTransientError,
)
from ai.ports.interfaces import StylePreferencesInput

VALID_SUGGESTIONS = {
    "suggestions": [
        {
            "item_category": "ethnic_kurta",
            "label": "Cotton Anarkali Kurta",
            "occasion": "festival",
            "rationale": "matches your ethnic style",
        }
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
        if callable(effect):
            return await effect()
        return effect


class _FakeAio:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


class _FakeClient:
    def __init__(self, side_effects: list[Any]) -> None:
        self.models = _FakeModels(side_effects)
        self.aio = _FakeAio(self.models)


def _valid_response(prompt_tokens: int = 100, output_tokens: int = 50) -> _FakeResponse:
    return _FakeResponse(json.dumps(VALID_SUGGESTIONS), _FakeUsage(prompt_tokens, output_tokens))


def _server_error() -> errors.ServerError:
    return errors.ServerError(503, {"message": "Service Unavailable", "status": "UNAVAILABLE"})


def _client_error_404() -> errors.ClientError:
    return errors.ClientError(404, {"message": "Not Found", "status": "NOT_FOUND"})


def _client_error_429() -> errors.ClientError:
    return errors.ClientError(429, {"message": "Too Many Requests", "status": "RESOURCE_EXHAUSTED"})


async def test_well_formed_json_succeeds_with_expected_source_and_model() -> None:
    fake_client = _FakeClient([_valid_response()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    result, metrics = await adapter.suggest_outfits_with_metrics(
        StylePreferencesInput(styles=["ethnic"])
    )

    assert result.source == "gemini"
    assert metrics.provider == "gemini"
    assert metrics.model == "gemini-2.5-flash-lite"
    assert metrics.tokens_in == 100
    assert metrics.tokens_out == 50
    assert len(result.suggestions) == 1


async def test_two_adapters_with_two_model_ids_call_the_sdk_with_those_exact_strings() -> None:
    fake_client_a = _FakeClient([_valid_response()])
    fake_client_b = _FakeClient([_valid_response()])
    adapter_a = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client_a)
    adapter_b = GeminiStylingAdapter(model="gemini-3.1-flash-lite", client=fake_client_b)

    await adapter_a.suggest_outfits(StylePreferencesInput())
    await adapter_b.suggest_outfits(StylePreferencesInput())

    assert fake_client_a.models.calls[0]["model"] == "gemini-2.5-flash-lite"
    assert fake_client_b.models.calls[0]["model"] == "gemini-3.1-flash-lite"


async def test_malformed_json_raises_provider_parse_error() -> None:
    fake_client = _FakeClient([_FakeResponse("not-json{{{")])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    with pytest.raises(ProviderParseError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_server_error_raises_provider_transient_error() -> None:
    fake_client = _FakeClient([_server_error()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    with pytest.raises(ProviderTransientError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_client_error_429_raises_provider_quota_exhausted_error() -> None:
    fake_client = _FakeClient([_client_error_429()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    with pytest.raises(ProviderQuotaExhaustedError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_client_error_404_raises_provider_permanent_error() -> None:
    fake_client = _FakeClient([_client_error_404()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    with pytest.raises(ProviderPermanentError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_none_response_text_raises_provider_parse_error_not_attribute_error() -> None:
    fake_client = _FakeClient([_FakeResponse(None)])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    with pytest.raises(ProviderParseError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_hanging_client_raises_provider_timeout_error_within_timeout_seconds() -> None:
    async def _hang() -> _FakeResponse:
        await asyncio.sleep(10)
        return _valid_response()

    fake_client = _FakeClient([_hang])
    adapter = GeminiStylingAdapter(
        model="gemini-2.5-flash-lite", client=fake_client, timeout_seconds=0.05
    )

    with pytest.raises(ProviderTimeoutError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_fallback_model_is_used_after_the_primary_model_fails() -> None:
    fake_client = _FakeClient([_client_error_404(), _valid_response()])
    adapter = GeminiStylingAdapter(
        model="gemini-2.5-flash-lite",
        client=fake_client,
        fallback_model="gemini-3.1-flash-lite",
    )

    result, metrics = await adapter.suggest_outfits_with_metrics(StylePreferencesInput())

    assert result.source == "gemini"
    assert metrics.model == "gemini-3.1-flash-lite"
    assert fake_client.models.calls[0]["model"] == "gemini-2.5-flash-lite"
    assert fake_client.models.calls[1]["model"] == "gemini-3.1-flash-lite"


async def test_missing_api_key_raises_provider_permanent_error_not_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite")

    with pytest.raises(ProviderPermanentError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_max_suggestions_enforced_by_slicing_not_only_prompt() -> None:
    payload = {
        "suggestions": [
            {"item_category": "ethnic_kurta", "label": f"Item {i}", "rationale": "r"}
            for i in range(5)
        ]
    }
    fake_client = _FakeClient([_FakeResponse(json.dumps(payload))])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    result = await adapter.suggest_outfits(StylePreferencesInput(), max_suggestions=2)

    assert len(result.suggestions) == 2


async def test_zero_suggestions_after_slicing_raises_provider_parse_error() -> None:
    fake_client = _FakeClient([_FakeResponse(json.dumps({"suggestions": []}))])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    with pytest.raises(ProviderParseError):
        await adapter.suggest_outfits_with_metrics(StylePreferencesInput())


async def test_empty_preferences_does_not_raise_and_is_not_personalized() -> None:
    fake_client = _FakeClient([_valid_response()])
    adapter = GeminiStylingAdapter(model="gemini-2.5-flash-lite", client=fake_client)

    result = await adapter.suggest_outfits(StylePreferencesInput())

    assert result.is_personalized is False
