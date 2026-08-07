"""Gemini styling adapter (SS-028) -- ``IStylingProvider`` + ``MeteredStylingProvider``.

Reuses ``gemini_vision_adapter.py``'s live-verified call shape (SS-012,
``[VERIFIED 2026-07-25]``): ``client.aio.models.generate_content(model=...,
contents=[...], config=types.GenerateContentConfig(response_mime_type=
"application/json", response_schema=<pydantic class>))``; ``response.text``
may be ``None``; ``errors.ClientError`` (4xx, has ``.code``) vs
``errors.ServerError`` (5xx, has ``.code``). That shape is re-used, not
re-verified, per design §9.2.

**Model ID note ``[VERIFIED 2026-07-30]``** (see
``services/ai_routing_specs.py`` and ``docs/worklog/SS-028.md``'s Developer
entry for the exact commands): a live call against the real
``GEMINI_API_KEY`` confirmed ``gemini-2.5-flash-lite`` -- the constructor
``model`` this adapter is normally given by the routing table -- returns
``google.genai.errors.ClientError(code=404, "... no longer available to new
users ...")`` for THIS account, even though it appears in
``client.aio.models.list()``. Shipped anyway per the user's explicit B1
decision. This is exactly why ``fallback_model`` exists: on ANY classified
failure of the primary ``model``, this adapter retries once, in-process,
against ``fallback_model`` (``EVERYDAY_FALLBACK_MODEL_ID`` =
``gemini-3.1-flash-lite``, live-verified callable against the same account)
before raising to the caller. This hop is entirely internal -- invisible to
``StylingRouter``'s attempt ladder and its per-attempt log line (design
§4.1: "a retry-hop detail inside the Gemini adapter's call logic, not a
slot in the routing table's JSON"). ``StylingCallMetrics.model`` always
reflects whichever model actually produced the result.

Explicit ``asyncio.wait_for`` at the call site, not the SDK's own
(documented-unreliable) ``HttpOptions.timeout`` -- same lesson as
``gemini_vision_adapter.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from ai.adapters.styling_call import (
    ProviderParseError,
    ProviderPermanentError,
    ProviderQuotaExhaustedError,
    ProviderTimeoutError,
    ProviderTransientError,
    StylingCallMetrics,
    is_effectively_empty,
)
from ai.adapters.styling_prompt import (
    NarrationPromptBuilder,
    StylingPromptBuilder,
    build_narration_prompt,
    build_styling_prompt,
)
from ai.ports.interfaces import (
    IStylingProvider,
    NarratedCandidate,
    NarratedPortfolioResult,
    OutfitSuggestionItem,
    OutfitSuggestionResult,
    StylePreferencesInput,
)

logger = logging.getLogger(__name__)


class _SuggestionsPayload(BaseModel):
    suggestions: list[OutfitSuggestionItem]


class _NarrationsPayload(BaseModel):
    narrations: list[NarratedCandidate]


class GeminiStylingAdapter(IStylingProvider):
    """``model`` is a REQUIRED constructor arg (AC #1 -- "use Flash-Lite vs
    use Sonnet is a config value, not a class"). ``client``/``timeout_seconds``/
    ``prompt_builder``/``fallback_model`` are all injectable."""

    def __init__(
        self,
        *,
        model: str,
        client: Any | None = None,
        timeout_seconds: float = 30.0,
        prompt_builder: StylingPromptBuilder = build_styling_prompt,
        fallback_model: str | None = None,
        narration_prompt_builder: NarrationPromptBuilder = build_narration_prompt,
    ) -> None:
        self._model = model
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._prompt_builder = prompt_builder
        self._fallback_model = fallback_model
        self._narration_prompt_builder = narration_prompt_builder

    def _get_client(self) -> Any:
        # Lazily constructed, never at import -- CI's dummy env stays
        # sufficient (mirrors GeminiVisionAdapter._get_client, N8).
        if self._client is not None:
            return self._client
        api_key = os.environ["GEMINI_API_KEY"]
        return genai.Client(api_key=api_key)

    async def suggest_outfits(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> OutfitSuggestionResult:
        result, _ = await self.suggest_outfits_with_metrics(
            preferences, max_suggestions=max_suggestions
        )
        return result

    async def suggest_outfits_with_metrics(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> tuple[OutfitSuggestionResult, StylingCallMetrics]:
        now_iso = datetime.now(UTC).isoformat()
        prompt = self._prompt_builder(preferences, max_suggestions=max_suggestions)

        models_to_try = [self._model]
        if self._fallback_model and self._fallback_model != self._model:
            models_to_try.append(self._fallback_model)

        last_error: Exception | None = None
        for model_id in models_to_try:
            try:
                return await self._attempt_once(
                    model_id, prompt, preferences, max_suggestions, now_iso
                )
            except (
                ProviderTransientError,
                ProviderQuotaExhaustedError,
                ProviderPermanentError,
                ProviderParseError,
                ProviderTimeoutError,
            ) as exc:
                last_error = exc
                continue
        assert last_error is not None  # models_to_try is never empty
        raise last_error

    async def narrate_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> NarratedPortfolioResult:
        result, _ = await self.narrate_candidates_with_metrics(
            candidates, occasion=occasion, preferences=preferences, max_suggestions=max_suggestions
        )
        return result

    async def narrate_candidates_with_metrics(
        self,
        candidates: list[dict[str, Any]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> tuple[NarratedPortfolioResult, StylingCallMetrics]:
        prompt = self._narration_prompt_builder(candidates, occasion, preferences, max_suggestions)

        models_to_try = [self._model]
        if self._fallback_model and self._fallback_model != self._model:
            models_to_try.append(self._fallback_model)

        last_error: Exception | None = None
        for model_id in models_to_try:
            try:
                return await self._attempt_narration_once(model_id, prompt, max_suggestions)
            except (
                ProviderTransientError,
                ProviderQuotaExhaustedError,
                ProviderPermanentError,
                ProviderParseError,
                ProviderTimeoutError,
            ) as exc:
                last_error = exc
                continue
        assert last_error is not None  # models_to_try is never empty
        raise last_error

    async def _attempt_narration_once(
        self, model_id: str, prompt: str, max_suggestions: int
    ) -> tuple[NarratedPortfolioResult, StylingCallMetrics]:
        start = time.perf_counter()
        try:
            client = self._get_client()
        except KeyError as exc:
            latency_ms = _elapsed_ms(start)
            logger.error(
                "gemini_narration_missing_api_key",
                extra={"model": model_id, "latency_ms": latency_ms},
            )
            raise ProviderPermanentError("gemini_api_key_missing") from exc

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_id,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=_NarrationsPayload,
                    ),
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "gemini_narration_timeout", extra={"model": model_id, "latency_ms": latency_ms}
            )
            raise ProviderTimeoutError(
                f"gemini narration call timed out after {self._timeout_seconds}s"
            ) from exc
        except errors.ServerError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "gemini_narration_server_error",
                extra={"model": model_id, "latency_ms": latency_ms, "code": exc.code},
            )
            raise ProviderTransientError(f"gemini server_error:{exc.code}") from exc
        except errors.ClientError as exc:
            latency_ms = _elapsed_ms(start)
            if exc.code == 429:
                logger.warning(
                    "gemini_narration_quota_exhausted",
                    extra={"model": model_id, "latency_ms": latency_ms},
                )
                raise ProviderQuotaExhaustedError(f"gemini client_error:{exc.code}") from exc
            logger.error(
                "gemini_narration_client_error",
                extra={"model": model_id, "latency_ms": latency_ms, "code": exc.code},
            )
            raise ProviderPermanentError(f"gemini client_error:{exc.code}") from exc

        latency_ms = _elapsed_ms(start)
        text = getattr(response, "text", None)
        if not text:
            logger.warning(
                "gemini_narration_empty_response",
                extra={"model": model_id, "latency_ms": latency_ms},
            )
            raise ProviderParseError("empty_or_blocked_response")

        try:
            payload = json.loads(text)
            parsed = _NarrationsPayload.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "gemini_narration_parse_failed",
                extra={"model": model_id, "latency_ms": latency_ms, "error": str(exc)},
            )
            raise ProviderParseError("parse_error") from exc

        narrations = parsed.narrations[: max(max_suggestions, 0)]
        if not narrations:
            logger.warning(
                "gemini_narration_zero_narrations",
                extra={"model": model_id, "latency_ms": latency_ms},
            )
            raise ProviderParseError("zero_narrations_after_slicing")

        usage = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)

        logger.info(
            "gemini_narration_call_success",
            extra={
                "model": model_id,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            },
        )

        result = NarratedPortfolioResult(narrations=narrations, language="en", source="gemini")
        metrics = StylingCallMetrics(
            provider="gemini",
            model=model_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        return result, metrics

    async def _attempt_once(
        self,
        model_id: str,
        prompt: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        now_iso: str,
    ) -> tuple[OutfitSuggestionResult, StylingCallMetrics]:
        start = time.perf_counter()
        try:
            client = self._get_client()
        except KeyError as exc:
            # N8: GEMINI_API_KEY unset -- classified here, at first USE, not
            # at import time (CI's dummy env stays sufficient). Never left
            # to raise into the router/BackgroundTasks callback (BL-096).
            latency_ms = _elapsed_ms(start)
            logger.error(
                "gemini_styling_missing_api_key",
                extra={"model": model_id, "latency_ms": latency_ms},
            )
            raise ProviderPermanentError("gemini_api_key_missing") from exc

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_id,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=_SuggestionsPayload,
                    ),
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "gemini_styling_timeout", extra={"model": model_id, "latency_ms": latency_ms}
            )
            raise ProviderTimeoutError(
                f"gemini call timed out after {self._timeout_seconds}s"
            ) from exc
        except errors.ServerError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "gemini_styling_server_error",
                extra={"model": model_id, "latency_ms": latency_ms, "code": exc.code},
            )
            raise ProviderTransientError(f"gemini server_error:{exc.code}") from exc
        except errors.ClientError as exc:
            latency_ms = _elapsed_ms(start)
            if exc.code == 429:
                logger.warning(
                    "gemini_styling_quota_exhausted",
                    extra={"model": model_id, "latency_ms": latency_ms},
                )
                raise ProviderQuotaExhaustedError(f"gemini client_error:{exc.code}") from exc
            logger.error(
                "gemini_styling_client_error",
                extra={"model": model_id, "latency_ms": latency_ms, "code": exc.code},
            )
            raise ProviderPermanentError(f"gemini client_error:{exc.code}") from exc

        latency_ms = _elapsed_ms(start)
        text = getattr(response, "text", None)
        if not text:
            # Empty/blocked-candidates response -- google-genai never raises
            # for this, `.text` just returns None (never an AttributeError).
            logger.warning(
                "gemini_styling_empty_response",
                extra={"model": model_id, "latency_ms": latency_ms},
            )
            raise ProviderParseError("empty_or_blocked_response")

        try:
            payload = json.loads(text)
            parsed = _SuggestionsPayload.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "gemini_styling_parse_failed",
                extra={"model": model_id, "latency_ms": latency_ms, "error": str(exc)},
            )
            raise ProviderParseError("parse_error") from exc

        suggestions = _enforce_max(parsed.suggestions, max_suggestions)
        if not suggestions:
            # N7: a well-formed empty (or all-sliced-away) list is treated as
            # the model not doing the job -- retry/failover, never a
            # silently-empty "success".
            logger.warning(
                "gemini_styling_zero_suggestions",
                extra={"model": model_id, "latency_ms": latency_ms},
            )
            raise ProviderParseError("zero_suggestions_after_slicing")

        usage = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)

        logger.info(
            "gemini_styling_call_success",
            extra={
                "model": model_id,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            },
        )

        result = OutfitSuggestionResult(
            user_id="",
            suggestions=suggestions,
            generated_at=now_iso,
            is_personalized=not is_effectively_empty(preferences),
            source="gemini",
        )
        metrics = StylingCallMetrics(
            provider="gemini",
            model=model_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        return result, metrics


def _enforce_max(
    suggestions: list[OutfitSuggestionItem], max_suggestions: int
) -> list[OutfitSuggestionItem]:
    return suggestions[: max(max_suggestions, 0)]


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
