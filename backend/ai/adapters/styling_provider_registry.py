"""Lazily constructs and caches one adapter instance per ``(provider,
model)`` pair (SS-028 design §3.1) -- this is what makes "any model the
config names works, with no redeploy" actually true: there is deliberately
no allow-list of known models (N3); the routing table itself IS the
allow-list, and a bogus ID simply surfaces as ``ProviderPermanentError`` on
first use rather than a startup-time or construction-time failure.

Client instances (one Gemini SDK client, one Anthropic SDK client) are
shared across every cached adapter for that provider, not re-created per
``(provider, model)`` pair -- matches ``GeminiVisionAdapter``'s own lazy
``_get_client()`` pattern, just hoisted one level so multiple model IDs for
the same provider don't each open a redundant client.
"""

from __future__ import annotations

import logging
from typing import Any

from ai.adapters.claude_styling_adapter import ClaudeStylingAdapter
from ai.adapters.gemini_styling_adapter import GeminiStylingAdapter
from ai.adapters.styling_call import MeteredStylingProvider
from ai.adapters.styling_prompt import StylingPromptBuilder, build_styling_prompt
from services.ai_routing_specs import EVERYDAY_FALLBACK_MODEL_ID

logger = logging.getLogger(__name__)


class StylingProviderRegistry:
    def __init__(
        self,
        *,
        gemini_client: Any | None = None,
        claude_client: Any | None = None,
        prompt_builder: StylingPromptBuilder = build_styling_prompt,
        gemini_fallback_model: str | None = EVERYDAY_FALLBACK_MODEL_ID,
    ) -> None:
        self._gemini_client = gemini_client
        self._claude_client = claude_client
        self._prompt_builder = prompt_builder
        self._gemini_fallback_model = gemini_fallback_model
        self._cache: dict[tuple[str, str], MeteredStylingProvider] = {}

    def get(self, provider: str, model: str) -> MeteredStylingProvider | None:
        """Returns ``None`` for an unrecognised provider KEY (N4) rather
        than raising -- ``StylingRouter`` treats that as an immediately-
        failed attempt and moves to the next provider in its failover
        chain, never a ``KeyError``."""
        key = (provider, model)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        adapter: MeteredStylingProvider
        if provider == "gemini":
            adapter = GeminiStylingAdapter(
                model=model,
                client=self._gemini_client,
                prompt_builder=self._prompt_builder,
                fallback_model=self._gemini_fallback_model,
            )
        elif provider == "claude":
            adapter = ClaudeStylingAdapter(
                model=model,
                client=self._claude_client,
                prompt_builder=self._prompt_builder,
            )
        else:
            logger.error(
                "styling_provider_registry_unknown_provider", extra={"provider": provider}
            )
            return None

        self._cache[key] = adapter
        return adapter
