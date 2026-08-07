"""Tests for backend/services/outfit_suggestion_service.py (SS-006)."""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from ai.ports.interfaces import (
    IStylingProvider,
    NarratedPortfolioResult,
    OutfitSuggestionItem,
    OutfitSuggestionResult,
    StylePreferencesInput,
)
from services.outfit_suggestion_service import OutfitSuggestionService
from services.rate_limiter import RateLimiter


class _FakeProvider(IStylingProvider):
    def __init__(self) -> None:
        self.calls: list[StylePreferencesInput] = []

    async def suggest_outfits(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> OutfitSuggestionResult:
        self.calls.append(preferences)
        return OutfitSuggestionResult(
            user_id="",
            suggestions=[
                OutfitSuggestionItem(
                    item_category="western_top", label="Test Item", rationale="test"
                )
            ],
            generated_at="2026-07-23T00:00:00+00:00",
            is_personalized=preferences.styles is not None,
            source="mock",
        )

    async def narrate_candidates(
        self,
        candidates: list[dict[str, object]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> NarratedPortfolioResult:
        return NarratedPortfolioResult(narrations=[], language="en", source="rules_only")


class _AlwaysAllowRateLimiter(RateLimiter):
    async def check_and_increment(self, user_id: str) -> bool:
        return True


class _AlwaysDenyRateLimiter(RateLimiter):
    async def check_and_increment(self, user_id: str) -> bool:
        return False


async def test_generate_suggestions_calls_provider_once_with_normalized_preferences() -> None:
    provider = _FakeProvider()
    service = OutfitSuggestionService(provider, rate_limiter=_AlwaysAllowRateLimiter())

    result = await service.generate_suggestions(
        "user-123", {"styles": ["ethnic"], "gender": "woman"}
    )

    assert len(provider.calls) == 1
    assert provider.calls[0].styles == ["ethnic"]
    assert provider.calls[0].gender == "woman"
    assert result.user_id == "user-123"


async def test_generate_suggestions_logs_user_id_tokens_used_latency_ms(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    service = OutfitSuggestionService(provider, rate_limiter=_AlwaysAllowRateLimiter())

    with caplog.at_level(logging.INFO):
        await service.generate_suggestions("user-456", None)

    ai_call_records = [r for r in caplog.records if r.message == "ai_call"]
    assert len(ai_call_records) == 1
    record = ai_call_records[0]
    assert record.user_id == "user-456"  # type: ignore[attr-defined]
    assert record.tokens_used == 0  # type: ignore[attr-defined]
    assert isinstance(record.latency_ms, int)  # type: ignore[attr-defined]


async def test_rate_limited_request_never_calls_provider_and_raises_429() -> None:
    provider = _FakeProvider()
    service = OutfitSuggestionService(provider, rate_limiter=_AlwaysDenyRateLimiter())

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_suggestions("user-789", None)

    assert exc_info.value.status_code == 429
    assert len(provider.calls) == 0


async def test_invalid_budget_range_degrades_to_empty_preferences() -> None:
    provider = _FakeProvider()
    service = OutfitSuggestionService(provider, rate_limiter=_AlwaysAllowRateLimiter())

    result = await service.generate_suggestions(
        "user-999", {"budget_range": "not_a_real_tier"}
    )

    assert len(provider.calls) == 1
    assert provider.calls[0].budget_range is None
    assert result.is_personalized is False
