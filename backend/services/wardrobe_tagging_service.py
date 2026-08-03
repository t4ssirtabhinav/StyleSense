"""Owns the full Gemini vision-tagging pipeline orchestration (SS-012):
fetch ``original.jpg`` from R2, MD5-hash it, check the Upstash result
cache, gate a fresh Gemini call behind a short-TTL in-flight marker + the
global 15 RPM rate limiter, derive review/moderation status, cache the raw
result, and write the columns + ``ai_tags.tagging`` back onto the
``wardrobe_items`` row -- all inside a single ``BackgroundTasks``-
dispatched call (never awaited directly from the request path, per
CLAUDE.md's "never call AI APIs synchronously").

Constructor-injected ``IVisionProvider``/``IWardrobeRepository`` (hexagonal
ports, per CLAUDE.md) plus concrete ``R2StorageClient``, ``TagCache``, and
``GeminiRateLimiter``.

Tags ``original.jpg`` (SS-010's 1200px-compressed upload), not
``clean.png`` -- deliberately decouples tagging from bg-removal
success/timing (SS-011's separate pipeline). Trade-off tracked as
``BL-063``.

**SS-029 addition:** every outcome of a tagging attempt reconciles the
router's pre-call reservation (``CostBudgetGate.reconcile``) and writes a
ledger row (``ICostLedger.record``) -- except the paths where NO Gemini
call happened at all (a cache hit still writes a zero-cost row; the
in-flight dedupe short-circuit writes NO row, just a full refund -- design
§5 edge cases 4/12). ``request_id``/``reservation``/``price_table`` are all
minted/read exactly ONCE by the router per request (design edge case 16)
and threaded through unchanged into this background task.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from adapters.interfaces import CostLedgerEntry, ICostLedger, IWardrobeRepository
from adapters.r2_storage import R2StorageClient
from ai.ports.interfaces import GarmentTags, IVisionProvider, TokenUsage
from services.cost_budget_gate import CostBudgetGate, Reservation
from services.gemini_rate_limiter import GeminiRateLimiter
from services.ist_window import ist_today
from services.occasion_normalizer import OccasionNormalizer
from services.price_table import PriceResolution, PriceTable
from services.tag_cache import TagCache

logger = logging.getLogger(__name__)

_CONFIDENCE_REVIEW_THRESHOLD = 0.7
_MODERATION_NULLING_FLAGS = {"nsfw", "other"}

FEATURE = "wardrobe_tagging"
PROVIDER = "gemini"
_CACHE_HIT_MODEL = "cache"


def original_image_key(user_id: str, item_id: str) -> str:
    return f"wardrobe/{user_id}/{item_id}/original.jpg"


class WardrobeTaggingService:
    def __init__(
        self,
        provider: IVisionProvider,
        repository: IWardrobeRepository,
        storage: R2StorageClient,
        cache: TagCache,
        rate_limiter: GeminiRateLimiter,
        occasion_normalizer: OccasionNormalizer,
        cost_budget_gate: CostBudgetGate,
        cost_ledger: ICostLedger,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._storage = storage
        self._cache = cache
        self._rate_limiter = rate_limiter
        self._occasion_normalizer = occasion_normalizer
        self._cost_budget_gate = cost_budget_gate
        self._cost_ledger = cost_ledger

    async def tag(
        self,
        *,
        jwt: str,
        user_id: str,
        item_id: str,
        request_id: str,
        reservation: Reservation,
        price_table: PriceTable,
    ) -> None:
        """The full pipeline for one item. Never raises -- any failure
        along the way is caught and results in ``ai_tags.tagging.status =
        'failed'`` rather than an unhandled background-task exception."""
        image_key = original_image_key(user_id, item_id)

        try:
            original_bytes = await asyncio.to_thread(self._storage.get_object_bytes, image_key)
        except Exception as exc:  # noqa: BLE001 - background task, must not raise
            logger.warning(
                "tagging_original_read_failed",
                extra={"user_id": user_id, "item_id": item_id, "error": str(exc)},
            )
            # No provider call ever happened -- full refund, no ledger row
            # (same treatment as the in-flight/skip short-circuits below).
            await self._cost_budget_gate.reconcile(reservation=reservation, actual_micropaise=0)
            await self._mark_failed(jwt=jwt, item_id=item_id)
            return

        image_hash = hashlib.md5(original_bytes).hexdigest()  # noqa: S324 - cache key, not security

        cached = await self._cache.get(image_hash)
        if cached is not None:
            try:
                cached_tags = GarmentTags.model_validate(cached)
            except Exception:  # noqa: BLE001 - corrupt/stale cache entry, treat as a miss
                cached_tags = None
            if cached_tags is not None:
                # Cache hits cost ~nothing but must still be RECORDED (design
                # edge case 4): zero-cost ledger row, full reservation
                # refund.
                await self._cost_budget_gate.reconcile(reservation=reservation, actual_micropaise=0)
                await self._record_ledger(
                    user_id=user_id,
                    request_id=request_id,
                    model=_CACHE_HIT_MODEL,
                    cost_resolution=PriceResolution(
                        cost_micropaise=0,
                        pricing_status="priced",
                        price_effective_from=None,
                        unit_price_snapshot={},
                    ),
                    tokens_in=None,
                    tokens_out=None,
                    latency_ms=None,
                    cache_hit=True,
                    outcome="success",
                )
                await self._write_success(
                    jwt=jwt,
                    user_id=user_id,
                    item_id=item_id,
                    tags=cached_tags,
                    source="cache",
                )
                return

        newly_marked = await self._cache.mark_inflight(image_hash)
        if not newly_marked:
            # A concurrent/retried call is already mid-flight for this
            # exact image -- short-circuit without calling Gemini again
            # (avoids double-charging for the same image). No provider call
            # happened here either -- full refund, no ledger row (design
            # edge case 12).
            logger.info("tagging_inflight_dedupe", extra={"user_id": user_id, "item_id": item_id})
            await self._cost_budget_gate.reconcile(reservation=reservation, actual_micropaise=0)
            return

        try:
            await self._rate_limiter.acquire()
            result = await self._provider.tag_garment(original_bytes)

            cost_resolution, tokens_in, tokens_out = _resolve_actual_cost(
                price_table, model=result.model, usage=result.usage
            )

            if not result.success or result.tags is None:
                logger.warning(
                    "tagging_provider_failed",
                    extra={"user_id": user_id, "item_id": item_id, "error": result.error},
                )
                # Design edge case 15: a failed-but-billed call. The model
                # may already have consumed tokens -- do NOT refund the
                # reservation, reconcile to the actual/estimated cost and
                # record it as 'failed'.
                await self._cost_budget_gate.reconcile(
                    reservation=reservation, actual_micropaise=cost_resolution.cost_micropaise
                )
                await self._record_ledger(
                    user_id=user_id,
                    request_id=request_id,
                    model=result.model,
                    cost_resolution=cost_resolution,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=result.latency_ms,
                    cache_hit=False,
                    outcome="failed",
                )
                await self._mark_failed(jwt=jwt, item_id=item_id)
                return

            await self._cache.set(image_hash, result.tags.model_dump(mode="json"))

            logger.info(
                "ai_call",
                extra={
                    "user_id": user_id,
                    "latency_ms": result.latency_ms,
                    "model": result.model,
                },
            )

            await self._cost_budget_gate.reconcile(
                reservation=reservation, actual_micropaise=cost_resolution.cost_micropaise
            )
            await self._record_ledger(
                user_id=user_id,
                request_id=request_id,
                model=result.model,
                cost_resolution=cost_resolution,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=result.latency_ms,
                cache_hit=False,
                outcome="success",
            )

            await self._write_success(
                jwt=jwt,
                user_id=user_id,
                item_id=item_id,
                tags=result.tags,
                source="gemini",
            )
        finally:
            # Always cleared, even on an exception above -- a crash between
            # mark and clear just lets the ~60s TTL expire the marker,
            # never leaving it permanently stuck (amended A1).
            await self._cache.clear_inflight(image_hash)

    async def _record_ledger(
        self,
        *,
        user_id: str,
        request_id: str,
        model: str,
        cost_resolution: PriceResolution,
        tokens_in: int | None,
        tokens_out: int | None,
        latency_ms: int | None,
        cache_hit: bool,
        outcome: str,
    ) -> None:
        # Defense in depth on top of ICostLedger.record's own "never raises"
        # contract (SupabaseCostLedger already guarantees it) -- an
        # accounting failure, even from a misbehaving adapter, must never
        # break the tagging pipeline whose AI call already happened (design
        # §4.3).
        try:
            await self._cost_ledger.record(
                CostLedgerEntry(
                    user_id=user_id,
                    request_id=request_id,
                    provider=PROVIDER,
                    model=model,
                    feature=FEATURE,
                    cost_micropaise=cost_resolution.cost_micropaise,
                    pricing_status=cost_resolution.pricing_status,
                    unit_price_snapshot=cost_resolution.unit_price_snapshot,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    cache_hit=cache_hit,
                    price_effective_from=cost_resolution.price_effective_from,
                    attempt=1,
                    outcome=outcome,
                )
            )
        except Exception as exc:  # noqa: BLE001 - never break tagging over an accounting failure
            logger.error(
                "ledger_write_failed",
                extra={"user_id": user_id, "request_id": request_id, "error": str(exc)},
            )

    async def _write_success(
        self, *, jwt: str, user_id: str, item_id: str, tags: GarmentTags, source: str
    ) -> None:
        flagged_for_review = tags.confidence < _CONFIDENCE_REVIEW_THRESHOLD
        moderation_flagged = tags.content_flag != "ok" or tags.contains_person
        status = "flagged" if (flagged_for_review or moderation_flagged) else "tagged"

        # Only an explicit nsfw/other flag nulls the category -- a garment
        # in a mirror-selfie (contains_person=true) is still a real
        # garment, and not_clothing already carries category=None from the
        # model's own prompt-instructed output.
        category = None if tags.content_flag in _MODERATION_NULLING_FLAGS else tags.category

        # (SS-025) Write boundary #1 of design §6.4's BL-078 matrix. Resolve
        # the model's occasion strings against the `occasions` registry
        # (canonical key -> alias -> keep-as-is) and dedupe, preserving
        # first-occurrence order. Never raises: a registry read failure
        # degrades to shape-only normalisation, and the DB trigger completes
        # the job on write.
        occasion_tags, unknown_occasions = await self._occasion_normalizer.normalize(
            list(tags.occasion_tags), jwt=jwt
        )

        # An unknown slug is an occasion we have not modelled yet, not an
        # error: it is STILL WRITTEN to the column (the DB trigger records it
        # in `occasion_unknown_tags` for product review) and logged here, one
        # record per slug. Nothing in this path drops the tag or fails the
        # item write -- that is the non-negotiable property.
        for slug in unknown_occasions:
            logger.warning(
                "occasion_unknown",
                extra={"user_id": user_id, "item_id": item_id, "slug": slug},
            )

        tag_columns: dict[str, Any] = {
            "category": category,
            "subcategory": tags.subcategory,
            "color_primary": tags.color_primary,
            "color_secondary": tags.color_secondary,
            "pattern": tags.pattern,
            "fabric": tags.fabric,
            "occasion_tags": occasion_tags,
            "season_tags": list(tags.season_tags),
        }

        await self._repository.update_tagging_result(
            jwt=jwt,
            item_id=item_id,
            tag_columns=tag_columns,
            tagging_tags=_tagging_payload(
                tags, status=status, source=source, flagged_for_review=flagged_for_review
            ),
        )

    async def _mark_failed(self, *, jwt: str, item_id: str) -> None:
        await self._repository.update_tagging_result(
            jwt=jwt,
            item_id=item_id,
            tag_columns=None,
            tagging_tags={"status": "failed"},
        )


def _resolve_actual_cost(
    price_table: PriceTable, *, model: str, usage: TokenUsage | None
) -> tuple[PriceResolution, int | None, int | None]:
    """Real usage -> priced/estimated from the actual token counts. No
    usage (SDK didn't expose it, or the call never reached a response) ->
    falls back to the price row's ``default_tokens_*`` estimate, but the
    result is FORCED to ``pricing_status='estimated'`` and the ledger's
    ``tokens_in``/``tokens_out`` stay ``None`` rather than writing a
    confidently-wrong token count (design §7 Q1)."""
    today = ist_today()
    if usage is not None:
        resolution = price_table.cost(
            provider=PROVIDER,
            model=model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            at=today,
        )
        return resolution, usage.tokens_in, usage.tokens_out

    logger.warning("tagging_usage_unavailable", extra={"model": model})
    resolution = price_table.estimate(provider=PROVIDER, model=model, at=today)
    if resolution.pricing_status == "priced":
        resolution = PriceResolution(
            cost_micropaise=resolution.cost_micropaise,
            pricing_status="estimated",
            price_effective_from=resolution.price_effective_from,
            unit_price_snapshot=resolution.unit_price_snapshot,
        )
    return resolution, None, None


def _tagging_payload(
    tags: GarmentTags, *, status: str, source: str, flagged_for_review: bool
) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "confidence": tags.confidence,
        "flagged_for_review": flagged_for_review,
        "alternatives": tags.alternatives,
        "moderation": {
            "content_flag": tags.content_flag,
            "contains_person": tags.contains_person,
        },
    }
