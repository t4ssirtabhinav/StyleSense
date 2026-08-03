"""Claude (Anthropic) styling adapter (SS-028) -- ``IStylingProvider`` +
``MeteredStylingProvider``.

**Call shape, ``[VERIFIED 2026-07-30]`` against the installed
``anthropic==0.116.0`` SDK source AND a live call against the real
``ANTHROPIC_API_KEY`` (see ``docs/worklog/SS-028.md``'s Developer entry for
the exact commands/output) -- nothing here was asserted from memory
(design §9.2 required this before writing this file):**

- ``anthropic.AsyncAnthropic(api_key=...)`` -- confirmed async client class
  and constructor kwarg.
- ``client.messages.create(model=..., max_tokens=..., messages=[...],
  tools=[...], tool_choice={"type": "tool", "name": ...})`` -- confirmed
  signature (``max_tokens``/``messages``/``model`` are the only required
  kwargs). ``model``'s accepted type is a ``Literal[...] | str`` union
  (``anthropic.types.model_param.ModelParam``) that literally lists
  ``"claude-sonnet-5"`` as a known value -- the exact API model ID string
  this adapter's ``HIGH_STAKES_MODEL_ID`` constant uses, matching the raw
  ticket's prose ("Claude Sonnet 5") exactly. A live call against the real
  key using this model id and this tool-use shape returned a valid
  ``tool_use`` content block.
- **Structured output mechanism**: Claude has no ``response_schema``
  equivalent to Gemini's -- the verified mechanism is forced tool use
  (``tool_choice={"type": "tool", "name": <tool name>}``), which makes
  ``response.content`` contain a ``ToolUseBlock`` whose ``.input`` is
  ALREADY a parsed ``dict`` (no ``json.loads`` needed, unlike the Gemini
  adapter's ``response.text`` string).
- **Usage/token attribute names**: ``response.usage.input_tokens`` /
  ``response.usage.output_tokens`` (``anthropic.types.usage.Usage``,
  confirmed via ``inspect.getsource``).
- **Error classes** (``anthropic._exceptions``, confirmed via source read):
  ``RateLimitError`` (``status_code == 429``, a subclass of
  ``APIStatusError`` -- caught FIRST, before the broader
  ``APIStatusError`` except clause) -> ``ProviderQuotaExhaustedError``;
  any other ``APIStatusError`` with ``status_code >= 500`` ->
  ``ProviderTransientError``; any other ``APIStatusError`` (4xx) ->
  ``ProviderPermanentError``; ``APIConnectionError`` (whose subclass
  ``APITimeoutError`` covers the SDK's own network-level timeout, distinct
  from this adapter's own ``asyncio.wait_for`` cutoff below) ->
  ``ProviderTransientError``.

Explicit ``asyncio.wait_for`` at the call site, same "don't trust the SDK's
own timeout" posture as ``gemini_vision_adapter.py``/``gemini_styling_adapter.py``.
No in-tier fallback-model hop here -- unlike Gemini, this design has exactly
ONE Claude model slot (``HIGH_STAKES_MODEL_ID``); a failure here goes
straight to ``StylingRouter``'s provider-level failover.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import anthropic
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
from ai.adapters.styling_prompt import StylingPromptBuilder, build_styling_prompt
from ai.ports.interfaces import (
    IStylingProvider,
    OutfitSuggestionItem,
    OutfitSuggestionResult,
    StylePreferencesInput,
)

logger = logging.getLogger(__name__)

_TOOL_NAME = "return_outfit_suggestions"
_TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_category": {"type": "string"},
                    "label": {"type": "string"},
                    "occasion": {"type": ["string", "null"]},
                    "rationale": {"type": "string"},
                },
                "required": ["item_category", "label", "rationale"],
            },
        }
    },
    "required": ["suggestions"],
}


class _SuggestionsPayload(BaseModel):
    suggestions: list[OutfitSuggestionItem]


class ClaudeStylingAdapter(IStylingProvider):
    """``model`` is a REQUIRED constructor arg, same as ``GeminiStylingAdapter``
    (AC #1). ``client``/``timeout_seconds``/``prompt_builder``/``max_tokens``
    are all injectable."""

    def __init__(
        self,
        *,
        model: str,
        client: Any | None = None,
        timeout_seconds: float = 30.0,
        prompt_builder: StylingPromptBuilder = build_styling_prompt,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._prompt_builder = prompt_builder
        self._max_tokens = max_tokens

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.environ["ANTHROPIC_API_KEY"]
        return anthropic.AsyncAnthropic(api_key=api_key)

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
        start = time.perf_counter()
        try:
            client = self._get_client()
        except KeyError as exc:
            # N8: ANTHROPIC_API_KEY unset -- classified here, at first USE,
            # not at import time. Never left to raise into the router/
            # BackgroundTasks callback (BL-096).
            latency_ms = _elapsed_ms(start)
            logger.error(
                "claude_styling_missing_api_key",
                extra={"model": self._model, "latency_ms": latency_ms},
            )
            raise ProviderPermanentError("claude_api_key_missing") from exc

        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[
                        {
                            "name": _TOOL_NAME,
                            "description": "Return structured outfit suggestions as JSON.",
                            "input_schema": _TOOL_INPUT_SCHEMA,
                        }
                    ],
                    tool_choice={"type": "tool", "name": _TOOL_NAME},
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "claude_styling_timeout",
                extra={"model": self._model, "latency_ms": latency_ms},
            )
            raise ProviderTimeoutError(
                f"claude call timed out after {self._timeout_seconds}s"
            ) from exc
        except anthropic.RateLimitError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "claude_styling_quota_exhausted",
                extra={"model": self._model, "latency_ms": latency_ms},
            )
            raise ProviderQuotaExhaustedError(f"claude status:{exc.status_code}") from exc
        except anthropic.APIStatusError as exc:
            latency_ms = _elapsed_ms(start)
            if exc.status_code >= 500:
                logger.warning(
                    "claude_styling_server_error",
                    extra={
                        "model": self._model,
                        "latency_ms": latency_ms,
                        "status_code": exc.status_code,
                    },
                )
                raise ProviderTransientError(f"claude status:{exc.status_code}") from exc
            logger.error(
                "claude_styling_client_error",
                extra={
                    "model": self._model,
                    "latency_ms": latency_ms,
                    "status_code": exc.status_code,
                },
            )
            raise ProviderPermanentError(f"claude status:{exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            latency_ms = _elapsed_ms(start)
            logger.warning(
                "claude_styling_connection_error",
                extra={"model": self._model, "latency_ms": latency_ms, "error": str(exc)},
            )
            raise ProviderTransientError("claude connection_error") from exc

        latency_ms = _elapsed_ms(start)

        tool_input: dict[str, Any] | None = None
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "tool_use":
                tool_input = block.input
                break

        if tool_input is None:
            logger.warning(
                "claude_styling_no_tool_use_block",
                extra={"model": self._model, "latency_ms": latency_ms},
            )
            raise ProviderParseError("no_tool_use_block")

        try:
            parsed = _SuggestionsPayload.model_validate(tool_input)
        except ValidationError as exc:
            logger.warning(
                "claude_styling_parse_failed",
                extra={"model": self._model, "latency_ms": latency_ms, "error": str(exc)},
            )
            raise ProviderParseError("parse_error") from exc

        suggestions = _enforce_max(parsed.suggestions, max_suggestions)
        if not suggestions:
            logger.warning(
                "claude_styling_zero_suggestions",
                extra={"model": self._model, "latency_ms": latency_ms},
            )
            raise ProviderParseError("zero_suggestions_after_slicing")

        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)

        logger.info(
            "claude_styling_call_success",
            extra={
                "model": self._model,
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
            source="claude",
        )
        metrics = StylingCallMetrics(
            provider="claude",
            model=self._model,
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
