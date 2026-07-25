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
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from adapters.interfaces import IWardrobeRepository
from adapters.r2_storage import R2StorageClient
from ai.ports.interfaces import GarmentTags, IVisionProvider
from services.gemini_rate_limiter import GeminiRateLimiter
from services.tag_cache import TagCache

logger = logging.getLogger(__name__)

_CONFIDENCE_REVIEW_THRESHOLD = 0.7
_MODERATION_NULLING_FLAGS = {"nsfw", "other"}


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
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._storage = storage
        self._cache = cache
        self._rate_limiter = rate_limiter

    async def tag(self, *, jwt: str, user_id: str, item_id: str) -> None:
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
                await self._write_success(
                    jwt=jwt, item_id=item_id, tags=cached_tags, source="cache"
                )
                return

        newly_marked = await self._cache.mark_inflight(image_hash)
        if not newly_marked:
            # A concurrent/retried call is already mid-flight for this
            # exact image -- short-circuit without calling Gemini again
            # (avoids double-charging for the same image).
            logger.info("tagging_inflight_dedupe", extra={"user_id": user_id, "item_id": item_id})
            return

        try:
            await self._rate_limiter.acquire()
            result = await self._provider.tag_garment(original_bytes)

            if not result.success or result.tags is None:
                logger.warning(
                    "tagging_provider_failed",
                    extra={"user_id": user_id, "item_id": item_id, "error": result.error},
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

            await self._write_success(jwt=jwt, item_id=item_id, tags=result.tags, source="gemini")
        finally:
            # Always cleared, even on an exception above -- a crash between
            # mark and clear just lets the ~60s TTL expire the marker,
            # never leaving it permanently stuck (amended A1).
            await self._cache.clear_inflight(image_hash)

    async def _write_success(
        self, *, jwt: str, item_id: str, tags: GarmentTags, source: str
    ) -> None:
        flagged_for_review = tags.confidence < _CONFIDENCE_REVIEW_THRESHOLD
        moderation_flagged = tags.content_flag != "ok" or tags.contains_person
        status = "flagged" if (flagged_for_review or moderation_flagged) else "tagged"

        # Only an explicit nsfw/other flag nulls the category -- a garment
        # in a mirror-selfie (contains_person=true) is still a real
        # garment, and not_clothing already carries category=None from the
        # model's own prompt-instructed output.
        category = None if tags.content_flag in _MODERATION_NULLING_FLAGS else tags.category

        tag_columns: dict[str, Any] = {
            "category": category,
            "subcategory": tags.subcategory,
            "color_primary": tags.color_primary,
            "color_secondary": tags.color_secondary,
            "pattern": tags.pattern,
            "fabric": tags.fabric,
            "occasion_tags": list(tags.occasion_tags),
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
