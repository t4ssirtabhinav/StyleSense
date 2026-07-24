"""Owns preference normalization, rate-limit checks, and AI-call logging for
the outfit-suggestion flow (SS-006).

Never calls a real AI provider synchronously from a request path -- the
router dispatches ``generate_suggestions`` via ``BackgroundTasks.add_task``
rather than awaiting it directly (CLAUDE.md: "Never call AI APIs
synchronously"). This holds even though ``MockStylingAdapter`` is instant,
so the calling convention doesn't change when a real (slow) adapter is
swapped in later.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from ai.ports.interfaces import IStylingProvider, OutfitSuggestionResult, StylePreferencesInput
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _normalize_preferences(raw_preferences: dict[str, Any] | None) -> StylePreferencesInput:
    """Parses raw (possibly null, partial, or malformed) JSONB-shaped
    preferences into a StylePreferencesInput, degrading to the empty/null
    preferences path instead of raising on invalid data.
    """
    if not raw_preferences:
        return StylePreferencesInput()
    try:
        return StylePreferencesInput.model_validate(raw_preferences)
    except ValidationError:
        logger.warning(
            "invalid_style_preferences_degraded",
            extra={"raw_preferences_keys": list(raw_preferences.keys())},
        )
        return StylePreferencesInput()


class OutfitSuggestionService:
    """Constructor-injected ``IStylingProvider`` -- depends on the port, never
    on a concrete adapter (Open/Closed, per CLAUDE.md)."""

    def __init__(
        self,
        provider: IStylingProvider,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._provider = provider
        # fail_open=True: this fallback only ever constructs a RateLimiter for
        # the MockStylingAdapter-only path (a real adapter should always be
        # given an explicit rate_limiter). Opt-in per SS-018 so this stays
        # zero-risk while RateLimiter's own default is fail-closed.
        self._rate_limiter = rate_limiter or RateLimiter(fail_open=True)

    async def generate_suggestions(
        self,
        user_id: str,
        raw_preferences: dict[str, Any] | None = None,
        *,
        max_suggestions: int = 5,
    ) -> OutfitSuggestionResult:
        """(1) Rate-limit check before touching the provider; (2) normalize
        preferences (null/partial/malformed -> degrade, never raise); (3)
        time the provider call and log user_id/tokens_used/latency_ms.
        """
        allowed = await self._rate_limiter.check_and_increment(user_id)
        if not allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly")

        preferences = _normalize_preferences(raw_preferences)

        start = time.perf_counter()
        result = await self._provider.suggest_outfits(preferences, max_suggestions=max_suggestions)
        latency_ms = int((time.perf_counter() - start) * 1000)

        result = result.model_copy(update={"user_id": user_id})

        # Mock adapter costs zero tokens; the log call site is exactly
        # where a real adapter's real token count would go.
        logger.info(
            "ai_call",
            extra={"user_id": user_id, "tokens_used": 0, "latency_ms": latency_ms},
        )

        return result
