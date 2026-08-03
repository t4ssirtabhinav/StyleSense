"""Shared, port-free support types for real ``IStylingProvider`` adapters
(SS-028 design §3.1).

Deliberately NOT in ``ai/ports/`` -- ``IStylingProvider`` itself is never
touched by this ticket (Open/Closed, per CLAUDE.md). Everything here is
either (a) a plain dataclass/exception hierarchy consumed by
``StylingRouter``'s attempt ladder, or (b) a ``typing.Protocol`` (structural,
not an ABC a class must explicitly subclass) describing the ONE extra method
real adapters add beyond the port -- ``suggest_outfits_with_metrics``. This
is the same "add a method, never widen the port" move used throughout this
design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ai.ports.interfaces import OutfitSuggestionResult, StylePreferencesInput


@dataclass(frozen=True)
class StylingCallMetrics:
    """One real provider attempt's cost/latency facts. Carries ``request_id``
    on the SS-029 hand-off side (StylingRouter attaches it when calling
    ``on_call`` -- this dataclass itself stays request-agnostic so a single
    adapter instance, cached by the registry across requests, never needs to
    know about any one request)."""

    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    attempt: int = 1


class ProviderCallError(Exception):
    """Base of the provider error hierarchy every real adapter raises
    instead of letting an SDK exception escape. ``StylingRouter``'s attempt
    ladder classifies on the concrete subclass, never on this base."""


class ProviderTransientError(ProviderCallError):
    """5xx / network. The router moves to the next provider in the chain
    immediately -- no same-provider retry (failover *is* the retry; a
    second call on a sick provider just spends the deadline)."""


class ProviderQuotaExhaustedError(ProviderCallError):
    """A provider-side 429 the local ``ProviderQuotaTracker`` ceiling did
    not predict. The router marks that provider quota-exhausted for the
    rest of THIS request and moves on -- never queues."""


class ProviderPermanentError(ProviderCallError):
    """4xx (bad model id, auth, ...). Logged at ERROR by the router -- a
    permanently-broken model ID in config is a config bug someone must
    see -- then the router moves to the next provider."""


class ProviderParseError(ProviderCallError):
    """Malformed/unparseable JSON, an empty/blocked response, or a
    well-formed-but-empty suggestion list (N7 -- "the model did not do the
    job" is treated the same as "the model returned garbage"). Retried once
    on the SAME provider (``parse_retry_attempts``), then treated as a
    failed attempt and failed over."""


class ProviderTimeoutError(ProviderCallError):
    """The adapter's own ``asyncio.wait_for`` cutoff (or the router's outer
    one) fired. Never retried on the same provider -- a call that already
    hung this long is not worth a second attempt against the same
    deadline."""


class MeteredStylingProvider(Protocol):
    """Structural protocol (NOT an ABC, NOT in ``ports/``) describing the
    one extra method real adapters add beyond ``IStylingProvider.suggest_outfits``.
    ``StylingProviderRegistry.get()`` returns this type; ``StylingRouter``
    depends on it, never on a concrete adapter class."""

    async def suggest_outfits_with_metrics(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> tuple[OutfitSuggestionResult, StylingCallMetrics]: ...


def is_effectively_empty(preferences: StylePreferencesInput) -> bool:
    """The SS-006 six-field "effectively empty preferences" predicate,
    promoted here (design §6.4) from ``ai/adapters/mock_styling_adapter.py``'s
    former private ``_is_effectively_empty`` so every real adapter shares
    the exact same check instead of re-implementing it a third time.
    ``mock_styling_adapter.py`` now imports this function -- the one
    acceptable edit to that file this ticket makes."""
    return (
        not preferences.styles
        and preferences.wardrobe_type is None
        and not preferences.occasions_priority
        and preferences.budget_range is None
        and not preferences.favourite_colours
        and preferences.gender is None
    )
