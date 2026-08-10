"""SS-020 -- ``OutfitPortfolioService``: the orchestrator behind
``POST /outfit-suggestions/portfolio``.

Owns the exact sequence from ``docs/tickets/SS-020-design.md`` section 2:
occasion resolution -> wardrobe fetch -> effort-tier resolution -> Engine v2
call -> cache lookup -> (on miss) budget reserve -> narration call -> cache
write -> budget reconcile -> session cost-outcome update -> response
assembly.

**Awaited synchronously inside the request handler** -- no ``BackgroundTasks``,
per the user's explicit 2026-08-07 sign-off on Open Question #1 (see
``docs/worklog/SS-020.md``). Every I/O call in this module is ``await``ed;
nothing here blocks the event loop with synchronous I/O.

Never a hard error to the caller for anything narration-related: an unknown
occasion, a zero-item wardrobe, a budget denial, a provider failure, or a
malformed LLM response all degrade to a still-``200`` response with
rule-based rationale text, never a 429/500 for those cases specifically
(auth/validation failures are the router's job, not this service's).
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, date, datetime
from typing import Any

from adapters.interfaces import ISuggestionLogRepository, IWardrobeRepository
from ai.ports.interfaces import SeasonTag, StylePreferencesInput
from services.ai_routing_specs import AI_ROUTER_POLICY_SPEC, AI_STYLING_ROUTING_TABLE_SPEC
from services.app_config import AppConfigService, AppConfigSnapshot
from services.app_config_specs import SUGGESTION_NARRATION_CACHE_TTL_SPEC
from services.cost_budget_gate import CostBudgetGate
from services.cost_config_specs import AI_PRICE_TABLE_SPEC
from services.engine_v2 import EngineV2
from services.engine_v2_effort_dial import resolve_effort_tier_for_request
from services.engine_v2_portfolio import compute_outfit_fingerprint
from services.ist_window import ist_today
from services.occasion_normalizer import OccasionNormalizer
from services.price_table import PriceTable
from services.provider_quota import ProviderQuotaTracker
from services.routing_mix_monitor import RoutingMixMonitor
from services.styling_router import RoutingContext, StylingRouter, resolve_route
from services.styling_rules_engine import render_candidate_for_prompt
from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput
from services.suggestion_narration_cache import (
    NarrationCacheOrchestrator,
    compute_candidate_shape,
    compute_narration_signature,
    signature_order,
)

logger = logging.getLogger(__name__)

_FALLBACK_OCCASION_KIND = "everyday"
_FALLBACK_OCCASION_FORMALITY = 5


class OutfitPortfolioService:
    def __init__(
        self,
        *,
        wardrobe_repo: IWardrobeRepository,
        occasion_normalizer: OccasionNormalizer,
        engine: EngineV2,
        app_config: AppConfigService,
        routing_mix_monitor: RoutingMixMonitor,
        cost_budget_gate: CostBudgetGate,
        provider_registry: Any,  # StylingProviderRegistry -- Any to avoid an ai/ <-> services/ import-direction violation
        provider_quota: ProviderQuotaTracker,
        narration_cache: NarrationCacheOrchestrator,
        suggestion_log_repo: ISuggestionLogRepository,
    ) -> None:
        self._wardrobe_repo = wardrobe_repo
        self._occasion_normalizer = occasion_normalizer
        self._engine = engine
        self._app_config = app_config
        self._routing_mix_monitor = routing_mix_monitor
        self._cost_budget_gate = cost_budget_gate
        self._provider_registry = provider_registry
        self._provider_quota = provider_quota
        self._narration_cache = narration_cache
        self._suggestion_log_repo = suggestion_log_repo

    async def generate_portfolio_for_request(
        self,
        *,
        user_id: str,
        jwt: str,
        occasion: str,
        season: SeasonTag | None,
        as_of: date | None,
        style_preferences_override: dict[str, Any] | None,
        config_snapshot: AppConfigSnapshot,
        exclude_fingerprints: list[str] | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        resolved_as_of = as_of or ist_today()

        occasion_input = await self._resolve_occasion(occasion, jwt=jwt)

        wardrobe_by_id = await self._fetch_wardrobe(jwt=jwt, user_id=user_id)
        preferences = await self._resolve_preferences(
            style_preferences_override, jwt=jwt, user_id=user_id
        )
        plan_tier = await self._wardrobe_repo.get_plan_tier(jwt=jwt, user_id=user_id)

        effort_tier_key, tier_params = await resolve_effort_tier_for_request(
            monitor=self._routing_mix_monitor,
            gate=self._cost_budget_gate,
            user_id=user_id,
            tier=plan_tier,
            config_snapshot=config_snapshot,
            app_config=self._app_config,
        )

        # (SS-023) Truncated at 60, oldest-first (design §1) -- an
        # over-cap list is TRUNCATED, never a 422. Empty/None both forward
        # as None so pre-SS-023 behaviour is reproduced byte-for-byte
        # (engine_v2_portfolio.select_portfolio's own "falsy = no-op" check).
        exclude_fp_set: frozenset[str] | None = (
            frozenset(exclude_fingerprints[:60]) if exclude_fingerprints else None
        )

        engine_result = await self._engine.generate_portfolio(
            list(wardrobe_by_id.values()),
            occasion_input,
            jwt=jwt,
            user_id=user_id,
            as_of=resolved_as_of,
            season=season,
            style_preferences=preferences,
            search_pool_size=tier_params.search_pool_size,
            mmr_lambda=tier_params.mmr_lambda,
            max_exploration=tier_params.max_exploration,
            effort_tier=effort_tier_key,
            tier=plan_tier,
            request_id=request_id,
            exclude_fingerprints=exclude_fp_set,
        )

        rationale_by_fingerprint: dict[str, str] = {}
        narration_language = "en"
        cache_hit = False
        cost_incurred = False

        if tier_params.llm_candidate_count is not None and engine_result.portfolio:
            try:
                (
                    rationale_by_fingerprint,
                    narration_language,
                    cache_hit,
                    cost_incurred,
                ) = await self._narrate(
                    engine_result_portfolio=engine_result.portfolio,
                    wardrobe_by_id=wardrobe_by_id,
                    occasion_input=occasion_input,
                    engine_version=engine_result.engine_version,
                    llm_candidate_count=tier_params.llm_candidate_count,
                    preferences=preferences,
                    plan_tier=plan_tier,
                    user_id=user_id,
                    request_id=request_id,
                    as_of=resolved_as_of,
                    config_snapshot=config_snapshot,
                )
            except Exception as exc:  # noqa: BLE001 -- narration must never fail the whole request
                logger.warning(
                    "outfit_portfolio_narration_failed",
                    extra={"user_id": user_id, "request_id": request_id, "error": str(exc)},
                )

        portfolio_response = []
        # (SS-023) `rank` is 1-based and EXACTLY the rank EngineV2._log_session
        # wrote to suggestion_impressions.rank for the same candidate -- both
        # loops iterate `engine_result.portfolio` in the same order with the
        # same `enumerate(..., start=1)`, so the join key is provably
        # identical, not coincidentally aligned (test plan item 2).
        for rank, pc in enumerate(engine_result.portfolio, start=1):
            candidate = pc.candidate
            fingerprint = compute_outfit_fingerprint(candidate.item_ids)
            rationale = rationale_by_fingerprint.get(fingerprint)
            rationale_language = narration_language if rationale is not None else "en"
            if rationale is None:
                # §2 step 11: rule-based fallback -- render_candidate_for_prompt's
                # own "explanation" field IS the two-highest-scoring-rule text.
                rationale = render_candidate_for_prompt(candidate)["explanation"]
            portfolio_response.append(
                {
                    "item_ids": list(candidate.item_ids),
                    "category_labels": dict(candidate.category_labels),
                    "total_score": candidate.total_score,
                    "rationale": rationale,
                    "rationale_language": rationale_language,
                    "is_exploration": pc.is_exploration,
                    "gap_flags": list(candidate.gap_flags),
                    "rank": rank,
                    "outfit_fingerprint": fingerprint,
                }
            )

        latency_ms = int((time.perf_counter() - start) * 1000)
        if engine_result.session_id is not None:
            try:
                await self._suggestion_log_repo.update_session_outcome(
                    session_id=engine_result.session_id,
                    cost_incurred=cost_incurred,
                    request_id=request_id,
                    latency_ms=latency_ms,
                )
            except Exception as exc:  # noqa: BLE001 -- logging must never fail the request
                logger.warning(
                    "outfit_portfolio_session_outcome_update_failed",
                    extra={"session_id": engine_result.session_id, "error": str(exc)},
                )

        return {
            "portfolio": portfolio_response,
            "limited_options": engine_result.limited_options,
            "gap_report": engine_result.gap_report.model_dump(),
            "engine_version": engine_result.engine_version,
            "effort_tier": effort_tier_key,
            "cache_hit": cache_hit,
            "generated_at": datetime.now(UTC).isoformat(),
            # (SS-023) session_id is None when EngineV2._log_session's
            # best-effort write failed -- a None session must still render
            # suggestions, it only means outcomes can't be recorded for this
            # batch (design §1/edge cases).
            "session_id": engine_result.session_id,
            "occasion_key": occasion_input.key,
        }

    async def _resolve_occasion(self, raw_occasion: str, *, jwt: str) -> OccasionStylingInput:
        """§2 step 1. An unresolvable/unknown occasion (not in
        ``snapshot.kinds``, no alias hit) still gets a full
        kind/formality/styling_rules triple -- degrades to
        ``kind="everyday", formality=5, styling_rules={}`` rather than a
        400/500 (mirrors ``default_styling_rules_for``'s own kind-based
        fallback philosophy). The occasion key itself is passed through
        VERBATIM (not replaced with a sentinel) so downstream novelty/
        gap-flag logging still records the unmodelled key for later review."""
        snapshot = await self._occasion_normalizer.get_registry(jwt=jwt)
        resolved_key = self._occasion_normalizer.resolve(raw_occasion, snapshot)
        if not resolved_key:
            resolved_key = _FALLBACK_OCCASION_KIND

        if resolved_key in snapshot.kinds:
            return OccasionStylingInput(
                key=resolved_key,
                kind=snapshot.kinds[resolved_key],  # type: ignore[arg-type]
                formality=snapshot.formalities.get(resolved_key, _FALLBACK_OCCASION_FORMALITY),
                styling_rules=snapshot.styling_rules.get(resolved_key, {}),
            )

        return OccasionStylingInput(
            key=resolved_key,
            kind=_FALLBACK_OCCASION_KIND,  # type: ignore[arg-type]
            formality=_FALLBACK_OCCASION_FORMALITY,
            styling_rules={},
        )

    async def _fetch_wardrobe(self, *, jwt: str, user_id: str) -> dict[str, WardrobeItemInput]:
        rows = await self._wardrobe_repo.get_items_for_styling(jwt=jwt, user_id=user_id)
        items: dict[str, WardrobeItemInput] = {}
        for row in rows:
            try:
                item = WardrobeItemInput.model_validate(row)
            except Exception as exc:  # noqa: BLE001 -- one malformed row must never fail the whole request
                logger.warning(
                    "outfit_portfolio_wardrobe_row_skipped",
                    extra={"user_id": user_id, "error": str(exc)},
                )
                continue
            items[item.id] = item
        return items

    async def _resolve_preferences(
        self, override: dict[str, Any] | None, *, jwt: str, user_id: str
    ) -> StylePreferencesInput:
        raw = override
        if raw is None:
            raw = await self._wardrobe_repo.get_style_preferences(jwt=jwt, user_id=user_id)
        if not raw:
            return StylePreferencesInput()
        try:
            return StylePreferencesInput.model_validate(raw)
        except Exception:  # noqa: BLE001 -- malformed preferences degrade, never fail the request
            logger.warning("outfit_portfolio_preferences_degraded", extra={"user_id": user_id})
            return StylePreferencesInput()

    async def _narrate(
        self,
        *,
        engine_result_portfolio: list[Any],
        wardrobe_by_id: dict[str, WardrobeItemInput],
        occasion_input: OccasionStylingInput,
        engine_version: str,
        llm_candidate_count: int,
        preferences: StylePreferencesInput,
        plan_tier: str,
        user_id: str,
        request_id: str,
        as_of: date,
        config_snapshot: AppConfigSnapshot,
    ) -> tuple[dict[str, str], str, bool, bool]:
        """§2 steps 8-11. Returns
        ``(rationale_by_fingerprint, language, cache_hit, cost_incurred)``."""
        top = sorted(
            engine_result_portfolio,
            key=lambda pc: (-pc.candidate.total_score, tuple(pc.candidate.item_ids)),
        )[:llm_candidate_count]

        shapes = [compute_candidate_shape(pc.candidate.item_ids, wardrobe_by_id) for pc in top]
        signature_hash = compute_narration_signature(
            shapes,
            occasion_key=occasion_input.key,
            engine_version=engine_version,
            llm_candidate_count=llm_candidate_count,
        )
        order = signature_order(shapes)  # order[sig_idx] -> position in `top`

        cached = await self._narration_cache.get(signature_hash=signature_hash)
        if cached is not None:
            rationale_by_fingerprint: dict[str, str] = {}
            for sig_idx, rationale in cached.narrations_by_signature_index.items():
                if 0 <= sig_idx < len(order):
                    top_pos = order[sig_idx]
                    fingerprint = compute_outfit_fingerprint(top[top_pos].candidate.item_ids)
                    rationale_by_fingerprint[fingerprint] = rationale
            return rationale_by_fingerprint, cached.language, True, False

        # Cache miss -> budget gate (§2 step 10).
        routing_table = self._app_config.read(config_snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
        policy = self._app_config.read(config_snapshot, AI_ROUTER_POLICY_SPEC)
        context = RoutingContext(
            user_id=user_id,
            request_id=request_id,
            tier=plan_tier,
            occasion=occasion_input.key,
            occasion_kind=occasion_input.kind,
            is_first_suggestion=False,
        )
        decision = resolve_route(routing_table, context)

        price_table = PriceTable(self._app_config.read(config_snapshot, AI_PRICE_TABLE_SPEC))
        estimate = price_table.estimate(provider=decision.provider, model=decision.model, at=as_of)

        gate_decision = await self._cost_budget_gate.reserve(
            user_id=user_id,
            tier=plan_tier,
            estimate_micropaise=estimate.cost_micropaise,
            config_snapshot=config_snapshot,
        )
        if not gate_decision.allowed:
            # Fail-closed free tier -- degrade to rule-based, NEVER a 429.
            return {}, "en", False, False

        assert gate_decision.reservation is not None  # allowed=True always carries one

        rendered_candidates = []
        for pc in top:
            rendered = render_candidate_for_prompt(pc.candidate)
            rendered["outfit_fingerprint"] = compute_outfit_fingerprint(pc.candidate.item_ids)
            rendered_candidates.append(rendered)

        # ``on_call`` is how the actual (real, metered) provider/model/token
        # counts reach this method -- StylingRouter's own
        # narrate_candidates_with_decision return shape (result, decision)
        # deliberately doesn't carry per-call token metrics (the router's
        # own log line/quota bookkeeping already consumes them internally),
        # so this is the one hook the router already exposes for a caller
        # that needs the real numbers for cost reconciliation.
        captured_metrics: list[Any] = []
        router = StylingRouter(
            registry=self._provider_registry,
            routing_table=routing_table,
            policy=policy,
            quota=self._provider_quota,
            monitor=self._routing_mix_monitor,
            context=context,
            snapshot_stale=config_snapshot.stale,
            on_call=lambda metrics, _decision: captured_metrics.append(metrics),
        )
        narrated_result, route_decision = await router.narrate_candidates_with_decision(
            rendered_candidates,
            occasion=occasion_input.key,
            preferences=preferences,
            max_suggestions=llm_candidate_count,
        )

        real_llm_call = narrated_result.source in ("gemini", "claude")
        if real_llm_call and captured_metrics:
            metrics = captured_metrics[-1]
            actual = price_table.cost(
                provider=route_decision.provider,
                model=metrics.model,
                tokens_in=metrics.tokens_in,
                tokens_out=metrics.tokens_out,
                at=as_of,
            )
            actual_micropaise = actual.cost_micropaise
        else:
            # StylingRouter's own degrade path fired (MockStylingAdapter) --
            # this happens AFTER a reservation was already made; reconcile
            # to the actual (near-zero, deterministic) cost so the
            # reservation isn't silently left inflated at the estimate.
            actual_micropaise = 0

        await self._cost_budget_gate.reconcile(
            reservation=gate_decision.reservation, actual_micropaise=actual_micropaise
        )

        fingerprint_to_rationale = {n.outfit_fingerprint: n.rationale for n in narrated_result.narrations}
        rationale_by_fingerprint = {}
        for pc in top:
            fp = compute_outfit_fingerprint(pc.candidate.item_ids)
            if fp in fingerprint_to_rationale:
                rationale_by_fingerprint[fp] = fingerprint_to_rationale[fp]

        if real_llm_call and rationale_by_fingerprint:
            narrations_by_signature_index: dict[int, str] = {}
            for sig_idx, top_pos in enumerate(order):
                fp = compute_outfit_fingerprint(top[top_pos].candidate.item_ids)
                if fp in fingerprint_to_rationale:
                    narrations_by_signature_index[sig_idx] = fingerprint_to_rationale[fp]
            if narrations_by_signature_index:
                ttl_seconds = self._app_config.read(
                    config_snapshot, SUGGESTION_NARRATION_CACHE_TTL_SPEC
                ).seconds
                await self._narration_cache.put(
                    signature_hash=signature_hash,
                    occasion_key=occasion_input.key,
                    engine_version=engine_version,
                    narrations_by_signature_index=narrations_by_signature_index,
                    language=narrated_result.language,
                    ttl_seconds=ttl_seconds,
                )

        return rationale_by_fingerprint, narrated_result.language, False, real_llm_call
