"""Tests for backend/ai/adapters/gemini_vision_adapter.py (SS-012, amended
A1), against a mocked ``google-genai`` client -- no real network/API-key
usage in this suite (a real live call was made separately, once, during the
Developer phase to verify the call shape -- see the adapter's own module
docstring and docs/worklog/SS-012.md; it is not repeated on every test run).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from google.genai import errors

from adapters.interfaces import IOccasionRepository, OccasionRegistrySnapshot
from ai.adapters.gemini_vision_adapter import MODEL, GeminiVisionAdapter
from services.occasion_normalizer import OccasionNormalizer

VALID_PAYLOAD = {
    "category": "ethnic_kurta",
    "subcategory": "straight-fit kurta",
    "color_primary": "#1E3A8A",
    "color_secondary": None,
    "pattern": "block_print",
    "fabric": "cotton",
    "occasion_tags": ["festival", "puja"],
    "season_tags": ["summer"],
    "confidence": 0.92,
    "content_flag": "ok",
    "contains_person": False,
    "alternatives": None,
}


class _FakeResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text


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


def _valid_response() -> _FakeResponse:
    return _FakeResponse(json.dumps(VALID_PAYLOAD))


def _server_error() -> errors.ServerError:
    return errors.ServerError(503, {"message": "Service Unavailable", "status": "UNAVAILABLE"})


def _client_error() -> errors.ClientError:
    return errors.ClientError(400, {"message": "Bad Request", "status": "INVALID_ARGUMENT"})


async def test_calls_client_with_expected_model_mime_type_prompt_and_image() -> None:
    fake_client = _FakeClient([_valid_response()])
    adapter = GeminiVisionAdapter(client=fake_client)

    await adapter.tag_garment(b"fake-image-bytes")

    assert len(fake_client.models.calls) == 1
    call = fake_client.models.calls[0]
    assert call["model"] == MODEL == "gemini-3.5-flash-lite"
    assert call["config"].response_mime_type == "application/json"
    # contents = [prompt_str, image_part]
    assert isinstance(call["contents"][0], str) and len(call["contents"][0]) > 0
    image_part = call["contents"][1]
    assert image_part.inline_data.data == b"fake-image-bytes"
    assert image_part.inline_data.mime_type == "image/jpeg"


async def test_valid_json_response_maps_through_to_a_successful_result() -> None:
    fake_client = _FakeClient([_valid_response()])
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is True
    assert result.tags is not None
    assert result.tags.category == "ethnic_kurta"
    assert result.tags.occasion_tags == ["festival", "puja"]
    assert result.tags.confidence == 0.92
    assert result.tags.content_flag == "ok"
    assert result.tags.contains_person is False
    assert result.source == "gemini"
    assert result.latency_ms is not None


class _FakeUsageMetadata:
    def __init__(self, prompt_token_count: int | None, candidates_token_count: int | None) -> None:
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count


class _FakeResponseWithUsage(_FakeResponse):
    def __init__(self, text: str | None, usage_metadata: _FakeUsageMetadata | None) -> None:
        super().__init__(text)
        self.usage_metadata = usage_metadata


async def test_successful_response_with_usage_metadata_populates_token_usage() -> None:
    """(SS-029) response.usage_metadata.prompt_token_count/
    candidates_token_count -- [VERIFIED 2026-07-30] against the installed
    google-genai==2.14.0 SDK's own types.py source (see
    ai/adapters/gemini_vision_adapter.py::_extract_usage's docstring)."""
    fake_client = _FakeClient(
        [_FakeResponseWithUsage(json.dumps(VALID_PAYLOAD), _FakeUsageMetadata(1234, 210))]
    )
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is True
    assert result.usage is not None
    assert result.usage.tokens_in == 1234
    assert result.usage.tokens_out == 210


async def test_response_without_usage_metadata_leaves_usage_none() -> None:
    fake_client = _FakeClient([_valid_response()])  # plain _FakeResponse, no usage_metadata attr
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is True
    assert result.usage is None


async def test_response_with_partial_usage_metadata_leaves_usage_none() -> None:
    fake_client = _FakeClient(
        [_FakeResponseWithUsage(json.dumps(VALID_PAYLOAD), _FakeUsageMetadata(1234, None))]
    )
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is True
    assert result.usage is None


async def test_malformed_non_json_output_returns_failure_without_raising() -> None:
    fake_client = _FakeClient([_FakeResponse("not valid json{{{")])
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is False
    assert result.error == "parse_error"


async def test_out_of_enum_category_returns_failure_without_raising() -> None:
    bad_payload = {**VALID_PAYLOAD, "category": "not_a_real_category"}
    fake_client = _FakeClient([_FakeResponse(json.dumps(bad_payload))])
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is False
    assert result.error == "parse_error"


async def test_safety_blocked_empty_candidates_returns_failure_not_retried() -> None:
    fake_client = _FakeClient([_FakeResponse(None)])
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is False
    assert result.error == "empty_or_blocked_response"
    assert len(fake_client.models.calls) == 1


async def test_timeout_returns_failure_without_raising() -> None:
    async def _hangs_forever() -> _FakeResponse:
        await asyncio.sleep(10)
        return _valid_response()  # pragma: no cover - never reached

    fake_client = _FakeClient([_hangs_forever])
    adapter = GeminiVisionAdapter(client=fake_client, timeout_seconds=0.05)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is False
    assert result.error == "timeout"


async def test_server_error_is_retried_up_to_the_bounded_count_then_fails() -> None:
    fake_client = _FakeClient([_server_error(), _server_error(), _server_error()])
    adapter = GeminiVisionAdapter(
        client=fake_client, max_attempts=3, retry_backoff_base_seconds=0.001
    )

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is False
    assert len(fake_client.models.calls) == 3
    assert result.error is not None and result.error.startswith("server_error")


async def test_client_error_is_never_retried() -> None:
    fake_client = _FakeClient([_client_error()])
    adapter = GeminiVisionAdapter(
        client=fake_client, max_attempts=3, retry_backoff_base_seconds=0.001
    )

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is False
    assert len(fake_client.models.calls) == 1
    assert result.error is not None and result.error.startswith("client_error")


# --- SS-025: registry-sourced occasion vocabulary in the prompt ------------


class _FakeOccasionRepository(IOccasionRepository):
    def __init__(self, keys: tuple[str, ...], *, fail: bool = False) -> None:
        self.calls = 0
        self._keys = keys
        self._fail = fail

    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        self.calls += 1
        if self._fail:
            raise RuntimeError("registry read failed")
        return OccasionRegistrySnapshot(keys=self._keys)


def _adapter_with_registry(
    fake_client: _FakeClient, keys: tuple[str, ...], *, fail: bool = False
) -> GeminiVisionAdapter:
    normalizer = OccasionNormalizer(_FakeOccasionRepository(keys, fail=fail), ttl_seconds=0.0)
    return GeminiVisionAdapter(
        client=fake_client, occasion_normalizer=normalizer, registry_jwt="caller-jwt"
    )


SEEDED_KEYS = (
    "office",
    "casual",
    "date_night",
    "wedding_guest",
    "festival",
    "puja",
    "party",
    "travel",
    "workout",
    "beach",
    "formal_event",
    "college",
)


async def test_prompt_contains_every_active_registry_key_in_sort_order() -> None:
    fake_client = _FakeClient([_valid_response()])
    adapter = _adapter_with_registry(fake_client, SEEDED_KEYS)

    await adapter.tag_garment(b"fake-image-bytes")

    prompt = fake_client.models.calls[0]["contents"][0]
    assert ", ".join(SEEDED_KEYS) in prompt
    for key in SEEDED_KEYS:
        assert key in prompt


async def test_a_newly_inserted_occasion_reaches_the_prompt_with_no_code_change() -> None:
    """The ticket's headline AC at the AI layer: inserting a row into
    `occasions` must change the vocabulary the model is given, with no
    rebuild, no redeploy and no edit to this adapter."""
    fake_client = _FakeClient([_valid_response()])
    adapter = _adapter_with_registry(fake_client, (*SEEDED_KEYS, "ganesh_chaturthi"))

    await adapter.tag_garment(b"fake-image-bytes")

    prompt = fake_client.models.calls[0]["contents"][0]
    assert "ganesh_chaturthi" in prompt
    # No placeholder survives into the rendered prompt.
    assert "{occasion_vocabulary}" not in prompt


async def test_prompt_renders_without_a_registry_and_never_blocks_tagging() -> None:
    fake_client = _FakeClient([_valid_response()])
    adapter = _adapter_with_registry(fake_client, (), fail=True)

    result = await adapter.tag_garment(b"fake-image-bytes")

    prompt = fake_client.models.calls[0]["contents"][0]
    assert "{occasion_vocabulary}" not in prompt
    assert result.success is True


async def test_response_with_an_unknown_occasion_still_succeeds_with_the_tag_retained() -> None:
    """The inverse of the pre-SS-025 behaviour: an occasion outside the
    registry no longer fails GarmentTags validation, so the whole payload
    survives and the tag reaches the item write."""
    payload = {**VALID_PAYLOAD, "occasion_tags": ["festival", "Ganesh Chaturthi"]}
    fake_client = _FakeClient([_FakeResponse(json.dumps(payload))])
    adapter = _adapter_with_registry(fake_client, SEEDED_KEYS)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is True
    assert result.tags is not None
    assert result.tags.occasion_tags == ["festival", "Ganesh Chaturthi"]


# --- SS-024: India-aware footwear vocabulary hint -------------------------


async def test_prompt_includes_india_footwear_vocabulary() -> None:
    """Cheap regression pin: the India-specific footwear values are the
    whole point of the prompt enrichment and are the first thing a future
    prompt edit would drop."""
    fake_client = _FakeClient([_valid_response()])
    adapter = GeminiVisionAdapter(client=fake_client)

    await adapter.tag_garment(b"fake-image-bytes")

    prompt = fake_client.models.calls[0]["contents"][0]
    assert "juti" in prompt
    assert "mojari" in prompt
    assert "kolhapuri" in prompt


async def test_footwear_subcategory_out_of_vocabulary_is_accepted() -> None:
    """Pins BL-064's lenient posture against a future strict-validation
    regression: an out-of-vocabulary footwear subcategory must still
    validate successfully, never nuke the whole payload."""
    payload = {
        **VALID_PAYLOAD,
        "category": "footwear_ethnic",
        "subcategory": "peshawari_chappal",
    }
    fake_client = _FakeClient([_FakeResponse(json.dumps(payload))])
    adapter = GeminiVisionAdapter(client=fake_client)

    result = await adapter.tag_garment(b"fake-image-bytes")

    assert result.success is True
    assert result.tags is not None
    assert result.tags.category == "footwear_ethnic"
    assert result.tags.subcategory == "peshawari_chappal"
