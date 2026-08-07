"""``StylingRouter`` -- a composite ``IStylingProvider`` that picks a real
provider+model per request (SS-028 design §6). Never modifies the port; a
richer, non-port method (``suggest_outfits_with_decision``) is how callers
that want the routing decision get it.

``resolve_route()`` is a pure function, no I/O, no adapters -- exhaustively
unit-testable against the routing-table matrix alone. ``StylingRouter``
itself does no I/O other than the injected ``registry``/``quota``/
``fallback`` -- it never reads ``occasions``, never normalises slugs, never
fetches config; whoever builds its ``RoutingContext`` and its
``routing_table``/``policy`` values (the composition root, i.e.
``routers/outfit_suggestions.py``) already resolved those from ONE
``AppConfigSnapshot`` per request (design §4.4) -- ``StylingRouter``'s own
constructor takes the already-read dataclasses, not the snapshot itself, so
a request can never observe two different routing tables across a
failover by construction.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from ai.adapters.mock_styling_adapter import MockStylingAdapter
from ai.adapters.styling_call import (
    MeteredStylingProvider,
    ProviderCallError,
    ProviderParseError,
    ProviderPermanentError,
    ProviderQuotaExhaustedError,
    ProviderTimeoutError,
    ProviderTransientError,
    StylingCallMetrics,
)
from ai.ports.interfaces import (
    IStylingProvider,
    NarratedPortfolioResult,
    OutfitSuggestionResult,
    StylePreferencesInput,
)
from services.ai_routing_specs import RouterPolicyConfig, RoutingTableConfig
from services.provider_quota import estimate_tokens

logger = logging.getLogger(__name__)

_KNOWN_WHEN_FIELDS = {"tier", "is_first_suggestion", "occasion", "occasion_kind"}

_OUTCOME_BY_ERROR: dict[type[Exception], str] = {
    ProviderTransientError: "transient",
    ProviderQuotaExhaustedError: "quota",
    ProviderPermanentError: "permanent",
    ProviderTimeoutError: "timeout",
}


class _RegistryLike(Protocol):
    def get(self, provider: str, model: str) -> MeteredStylingProvider | None: ...


class _QuotaLike(Protocol):
    async def try_reserve(self, provider: str, *, estimated_tokens: int) -> bool: ...

    async def record_usage(self, provider: str, *, tokens_in: int, tokens_out: int) -> None: ...


class _MonitorLike(Protocol):
    def record(self, decision: RoutingDecision, outcome: str) -> None: ...


@dataclass(frozen=True)
class RoutingContext:
    """Constructed PER REQUEST. Constructor injection of per-request
    context, exactly the precedent ``GeminiVisionAdapter`` set in SS-012
    (``occasion_normalizer``/``registry_jwt``) specifically to avoid
    changing a port signature."""

    user_id: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tier: str = "free"
    occasion: str | None = None
    occasion_kind: str | None = None
    is_first_suggestion: bool = False


@dataclass(frozen=True)
class RoutingDecision:
    provider: str
    model: str
    cost_class: str
    reason: str
    table_version: int
    matched_rule_index: int | None = None


def resolve_route(table: RoutingTableConfig, context: RoutingContext) -> RoutingDecision:
    """Pure, no I/O. Rules evaluated in array order, first match wins; if
    none match, ``table.default`` is used. Inside one ``when``, every
    stated field must match (AND) -- a list field matches by membership,
    ``is_first_suggestion`` by equality; an ABSENT field (not in ``when``)
    is a wildcard. An unknown field inside ``when`` makes that ONE rule
    inert (skipped, logged at WARNING) -- never invalidates the whole
    table."""
    for index, rule in enumerate(table.rules):
        if _rule_matches(rule.when, context):
            route = rule.route
            return RoutingDecision(
                provider=route.provider,
                model=route.model,
                cost_class=route.cost_class,
                reason=route.reason,
                table_version=table.version,
                matched_rule_index=index,
            )

    default = table.default
    return RoutingDecision(
        provider=default.provider,
        model=default.model,
        cost_class=default.cost_class,
        reason=default.reason,
        table_version=table.version,
        matched_rule_index=None,
    )


def _rule_matches(when: dict[str, object], context: RoutingContext) -> bool:
    unknown_fields = set(when.keys()) - _KNOWN_WHEN_FIELDS
    if unknown_fields:
        logger.warning(
            "styling_router_unknown_when_field", extra={"fields": sorted(unknown_fields)}
        )
        return False

    for field_name, expected in when.items():
        actual = getattr(context, field_name)
        if field_name == "is_first_suggestion":
            if actual != expected:
                return False
        else:
            if actual is None or not isinstance(expected, list) or actual not in expected:
                return False
    return True


class StylingRouter(IStylingProvider):
    def __init__(
        self,
        *,
        registry: _RegistryLike,
        routing_table: RoutingTableConfig,
        policy: RouterPolicyConfig,
        quota: _QuotaLike,
        monitor: _MonitorLike,
        context: RoutingContext,
        fallback: IStylingProvider | None = None,
        snapshot_stale: bool = False,
        clock: Callable[[], float] | None = None,
        on_call: Callable[[StylingCallMetrics, RoutingDecision], None] | None = None,
    ) -> None:
        self._registry = registry
        self._routing_table = routing_table
        self._policy = policy
        self._quota = quota
        self._monitor = monitor
        self._context = context
        self._fallback = fallback if fallback is not None else MockStylingAdapter()
        self._snapshot_stale = snapshot_stale
        self._clock = clock or time.monotonic
        self._on_call = on_call

    async def suggest_outfits(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> OutfitSuggestionResult:
        result, _decision = await self.suggest_outfits_with_decision(
            preferences, max_suggestions=max_suggestions
        )
        return result

    async def suggest_outfits_with_decision(
        self,
        preferences: StylePreferencesInput,
        *,
        max_suggestions: int = 5,
    ) -> tuple[OutfitSuggestionResult, RoutingDecision]:
        decision = resolve_route(self._routing_table, self._context)
        chain = self._build_chain(decision.provider)
        provider_model = self._provider_model_map()

        start = self._clock()
        attempt = 0
        estimated_tokens = estimate_tokens(_estimate_prompt_len(preferences))

        for provider in chain:
            if self._deadline_exceeded(start):
                break

            model = provider_model.get(provider)
            if model is None:
                attempt += 1
                self._log_and_record(
                    decision=decision,
                    attempt=attempt,
                    provider=provider,
                    model="unknown",
                    outcome="permanent",
                    routing_reason=f"{decision.reason}:unknown_provider_in_table",
                    latency_ms=0,
                    level=logging.ERROR,
                )
                continue

            adapter = self._registry.get(provider, model)
            if adapter is None:
                attempt += 1
                self._log_and_record(
                    decision=decision,
                    attempt=attempt,
                    provider=provider,
                    model=model,
                    outcome="permanent",
                    routing_reason=f"{decision.reason}:unknown_provider",
                    latency_ms=0,
                    level=logging.ERROR,
                )
                continue

            parse_retries_used = 0
            while True:
                if self._deadline_exceeded(start):
                    return await self._degrade(preferences, max_suggestions, decision)

                reserved = await self._quota.try_reserve(
                    provider, estimated_tokens=estimated_tokens
                )
                attempt += 1
                if not reserved:
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome="quota",
                        routing_reason=f"{decision.reason}:quota_exhausted",
                        latency_ms=0,
                    )
                    break  # next provider in chain

                call_start = self._clock()
                try:
                    result, metrics = await asyncio.wait_for(
                        adapter.suggest_outfits_with_metrics(
                            preferences, max_suggestions=max_suggestions
                        ),
                        timeout=self._policy.attempt_timeout_seconds,
                    )
                except TimeoutError:
                    latency_ms = int((self._clock() - call_start) * 1000)
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome="timeout",
                        routing_reason=decision.reason,
                        latency_ms=latency_ms,
                    )
                    break  # next provider
                except ProviderParseError:
                    latency_ms = int((self._clock() - call_start) * 1000)
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome="parse_error",
                        routing_reason=decision.reason,
                        latency_ms=latency_ms,
                    )
                    parse_retries_used += 1
                    if parse_retries_used <= self._policy.parse_retry_attempts:
                        continue  # same-provider retry
                    break  # next provider
                except ProviderCallError as exc:
                    latency_ms = int((self._clock() - call_start) * 1000)
                    outcome = _OUTCOME_BY_ERROR.get(type(exc), "transient")
                    level = logging.ERROR if outcome == "permanent" else logging.INFO
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome=outcome,
                        routing_reason=decision.reason,
                        latency_ms=latency_ms,
                        level=level,
                    )
                    break  # next provider
                else:
                    await self._quota.record_usage(
                        provider, tokens_in=metrics.tokens_in, tokens_out=metrics.tokens_out
                    )
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=metrics.model,
                        outcome="success",
                        routing_reason=decision.reason,
                        latency_ms=metrics.latency_ms,
                        tokens_in=metrics.tokens_in,
                        tokens_out=metrics.tokens_out,
                    )
                    if self._on_call is not None:
                        self._on_call(metrics, decision)
                    return result, decision

        return await self._degrade(preferences, max_suggestions, decision)

    async def narrate_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> NarratedPortfolioResult:
        result, _decision = await self.narrate_candidates_with_decision(
            candidates, occasion=occasion, preferences=preferences, max_suggestions=max_suggestions
        )
        return result

    async def narrate_candidates_with_decision(
        self,
        candidates: list[dict[str, Any]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
    ) -> tuple[NarratedPortfolioResult, RoutingDecision]:
        """Reuses the exact chain/failover/quota/timeout/degrade structure
        ``suggest_outfits_with_decision`` uses -- ``_build_chain``,
        ``_deadline_exceeded``, ``_log_and_record`` all shared, unchanged."""
        decision = resolve_route(self._routing_table, self._context)
        chain = self._build_chain(decision.provider)
        provider_model = self._provider_model_map()

        start = self._clock()
        attempt = 0
        estimated_tokens = estimate_tokens(_estimate_prompt_len(preferences) + len(str(candidates)))

        for provider in chain:
            if self._deadline_exceeded(start):
                break

            model = provider_model.get(provider)
            if model is None:
                attempt += 1
                self._log_and_record(
                    decision=decision,
                    attempt=attempt,
                    provider=provider,
                    model="unknown",
                    outcome="permanent",
                    routing_reason=f"{decision.reason}:unknown_provider_in_table",
                    latency_ms=0,
                    level=logging.ERROR,
                )
                continue

            adapter = self._registry.get(provider, model)
            if adapter is None:
                attempt += 1
                self._log_and_record(
                    decision=decision,
                    attempt=attempt,
                    provider=provider,
                    model=model,
                    outcome="permanent",
                    routing_reason=f"{decision.reason}:unknown_provider",
                    latency_ms=0,
                    level=logging.ERROR,
                )
                continue

            parse_retries_used = 0
            while True:
                if self._deadline_exceeded(start):
                    return await self._degrade_narration(
                        candidates, occasion, preferences, max_suggestions, decision
                    )

                reserved = await self._quota.try_reserve(
                    provider, estimated_tokens=estimated_tokens
                )
                attempt += 1
                if not reserved:
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome="quota",
                        routing_reason=f"{decision.reason}:quota_exhausted",
                        latency_ms=0,
                    )
                    break  # next provider in chain

                call_start = self._clock()
                try:
                    result, metrics = await asyncio.wait_for(
                        adapter.narrate_candidates_with_metrics(
                            candidates,
                            occasion=occasion,
                            preferences=preferences,
                            max_suggestions=max_suggestions,
                        ),
                        timeout=self._policy.attempt_timeout_seconds,
                    )
                except TimeoutError:
                    latency_ms = int((self._clock() - call_start) * 1000)
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome="timeout",
                        routing_reason=decision.reason,
                        latency_ms=latency_ms,
                    )
                    break  # next provider
                except ProviderParseError:
                    latency_ms = int((self._clock() - call_start) * 1000)
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome="parse_error",
                        routing_reason=decision.reason,
                        latency_ms=latency_ms,
                    )
                    parse_retries_used += 1
                    if parse_retries_used <= self._policy.parse_retry_attempts:
                        continue  # same-provider retry
                    break  # next provider
                except ProviderCallError as exc:
                    latency_ms = int((self._clock() - call_start) * 1000)
                    outcome = _OUTCOME_BY_ERROR.get(type(exc), "transient")
                    level = logging.ERROR if outcome == "permanent" else logging.INFO
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=model,
                        outcome=outcome,
                        routing_reason=decision.reason,
                        latency_ms=latency_ms,
                        level=level,
                    )
                    break  # next provider
                else:
                    await self._quota.record_usage(
                        provider, tokens_in=metrics.tokens_in, tokens_out=metrics.tokens_out
                    )
                    self._log_and_record(
                        decision=decision,
                        attempt=attempt,
                        provider=provider,
                        model=metrics.model,
                        outcome="success",
                        routing_reason=decision.reason,
                        latency_ms=metrics.latency_ms,
                        tokens_in=metrics.tokens_in,
                        tokens_out=metrics.tokens_out,
                    )
                    if self._on_call is not None:
                        self._on_call(metrics, decision)
                    return result, decision

        return await self._degrade_narration(
            candidates, occasion, preferences, max_suggestions, decision
        )

    def _deadline_exceeded(self, start: float) -> bool:
        elapsed = self._clock() - start
        return elapsed + self._policy.attempt_timeout_seconds > self._policy.total_deadline_seconds

    def _build_chain(self, primary_provider: str) -> list[str]:
        """[primary] + its configured failover chain, de-duplicated so a
        self-referential or cyclic ``failover`` map still attempts each
        provider at most once (N5)."""
        chain = [primary_provider]
        for candidate in self._routing_table.failover.get(primary_provider, []):
            if candidate not in chain:
                chain.append(candidate)
        return chain

    def _provider_model_map(self) -> dict[str, str]:
        """Derives a provider -> model map from the routing table's own
        ``default`` + ``rules`` (every route for a given provider uses the
        same model throughout this design's shipped table). This is what
        decides which MODEL a failover hop to a DIFFERENT provider than the
        original decision uses -- the routing table's own ``failover`` key
        only names provider IDs, not models, so this reads the model each
        provider is actually configured with elsewhere in the same table
        rather than inventing one. Pure, derived from the already-resolved
        ``routing_table`` -- no extra I/O."""
        mapping: dict[str, str] = {self._routing_table.default.provider: self._routing_table.default.model}
        for rule in self._routing_table.rules:
            mapping[rule.route.provider] = rule.route.model
        return mapping

    async def _degrade(
        self,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        decision: RoutingDecision,
    ) -> tuple[OutfitSuggestionResult, RoutingDecision]:
        """§6.2 step 6/7. Never raises -- this is the router's contract even
        though individual adapters do raise (BL-096: a raise inside a
        ``BackgroundTasks`` callback is a live crash class in this repo)."""
        self._log_and_record(
            decision=decision,
            attempt=0,
            provider="none",
            model="none",
            outcome="degraded",
            routing_reason="degraded_all_providers_failed",
            latency_ms=0,
            degraded=True,
            level=logging.WARNING,
        )
        try:
            result = await self._fallback.suggest_outfits(
                preferences, max_suggestions=max_suggestions
            )
            return result, decision
        except Exception:  # noqa: BLE001 - the degrade path itself must never raise
            logger.exception(
                "ai_styling_fallback_failed",
                extra={"request_id": self._context.request_id, "user_id": self._context.user_id},
            )
            empty_result = OutfitSuggestionResult(
                user_id=self._context.user_id,
                suggestions=[],
                generated_at=datetime.now(UTC).isoformat(),
                is_personalized=False,
                source="mock",
            )
            return empty_result, decision

    async def _degrade_narration(
        self,
        candidates: list[dict[str, Any]],
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        decision: RoutingDecision,
    ) -> tuple[NarratedPortfolioResult, RoutingDecision]:
        """Narration sibling of ``_degrade`` -- calls
        ``self._fallback.narrate_candidates(...)`` (``MockStylingAdapter`` by
        default), whose implementation is the rule-based degrade described
        in ``mock_styling_adapter.py``. This satisfies the AC's "never a
        hard error to the user" for the narration leg by construction, the
        same way ``_degrade`` already does for ``suggest_outfits``."""
        self._log_and_record(
            decision=decision,
            attempt=0,
            provider="none",
            model="none",
            outcome="degraded",
            routing_reason="degraded_all_providers_failed",
            latency_ms=0,
            degraded=True,
            level=logging.WARNING,
        )
        try:
            result = await self._fallback.narrate_candidates(
                candidates,
                occasion=occasion,
                preferences=preferences,
                max_suggestions=max_suggestions,
            )
            return result, decision
        except Exception:  # noqa: BLE001 - the degrade path itself must never raise
            logger.exception(
                "ai_narration_fallback_failed",
                extra={"request_id": self._context.request_id, "user_id": self._context.user_id},
            )
            return NarratedPortfolioResult(narrations=[], language="en", source="rules_only"), decision

    def _log_and_record(
        self,
        *,
        decision: RoutingDecision,
        attempt: int,
        provider: str,
        model: str,
        outcome: str,
        routing_reason: str,
        latency_ms: int,
        tokens_in: int = 0,
        tokens_out: int = 0,
        degraded: bool = False,
        level: int = logging.INFO,
    ) -> None:
        logger.log(
            level,
            "ai_styling_call",
            extra={
                "request_id": self._context.request_id,
                "user_id": self._context.user_id,
                "provider": provider,
                "model": model,
                "cost_class": decision.cost_class,
                "routing_reason": routing_reason,
                "table_version": decision.table_version,
                "attempt": attempt,
                "outcome": outcome,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokens_used": tokens_in + tokens_out,
                "latency_ms": latency_ms,
                "degraded": degraded,
                "config_stale": self._snapshot_stale,
            },
        )
        self._monitor.record(decision, outcome)


def _estimate_prompt_len(preferences: StylePreferencesInput) -> int:
    """A rough proxy for the eventual prompt's character length -- +800
    approximates the static instruction/template prose every prompt carries
    regardless of preferences (``ai/adapters/styling_prompt.py``'s fixed
    text). Documented as an ESTIMATE (``services/provider_quota.py``'s own
    docstring already labels the whole calculation as one) -- the router
    never sees the adapter's actual rendered prompt, by design (no I/O of
    its own)."""
    return len(preferences.model_dump_json()) + 800
