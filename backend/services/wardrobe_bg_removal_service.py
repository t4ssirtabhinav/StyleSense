"""Owns the full BG-removal pipeline orchestration (SS-011): fetch the
original image from R2, decide whether to call Replicate at all (cost-saving
heuristic / circuit breaker), call the provider, generate a thumbnail, write
both results back to R2, and update the ``wardrobe_items`` row -- all inside
a single ``BackgroundTasks``-dispatched call (never awaited directly from the
request path, per CLAUDE.md's "never call AI APIs synchronously").

Constructor-injected ``IBackgroundRemovalProvider``/``IWardrobeRepository``
(hexagonal ports, per CLAUDE.md) plus a concrete ``R2StorageClient`` and
``CircuitBreaker``. Also owns an in-process ``asyncio.Semaphore(3)`` capping
concurrent Replicate calls regardless of how many ``remove-bg`` requests a
client batch fires in parallel (addresses the ticket's own "batch of 10,
queue sequentially" edge case). **Known limitation, not fixed here:** this is
in-process state -- correct for today's single-``uvicorn``-process reality,
compounds with ``BL-037`` if this backend is ever deployed with >1 worker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from adapters.interfaces import IWardrobeRepository
from adapters.r2_storage import R2StorageClient
from ai.ports.interfaces import IBackgroundRemovalProvider
from services.circuit_breaker import CircuitBreaker
from services.image_processing import (
    apply_alpha_mask_to_original,
    generate_thumbnail,
    is_low_confidence,
    looks_already_transparent_or_white,
    resize_for_bg_removal,
)

logger = logging.getLogger(__name__)

# Mirrors ai/adapters/replicate_bg_removal_adapter.py's own constant -- kept
# duplicated rather than imported to avoid this orchestration service
# depending on a concrete adapter (it only depends on the
# IBackgroundRemovalProvider port). Both values must stay in sync with
# Replicate's actual per-run price.
COST_USD_PER_RUN = 0.0023


def original_image_key(user_id: str, item_id: str) -> str:
    return f"wardrobe/{user_id}/{item_id}/original.jpg"


def clean_image_key(user_id: str, item_id: str) -> str:
    return f"wardrobe/{user_id}/{item_id}/clean.png"


def thumbnail_image_key(user_id: str, item_id: str) -> str:
    return f"wardrobe/{user_id}/{item_id}/thumbnail.jpg"


class WardrobeBgRemovalService:
    def __init__(
        self,
        provider: IBackgroundRemovalProvider,
        repository: IWardrobeRepository,
        storage: R2StorageClient,
        circuit_breaker: CircuitBreaker,
        *,
        max_concurrent_replicate_calls: int = 3,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._storage = storage
        self._circuit_breaker = circuit_breaker
        self._semaphore = asyncio.Semaphore(max_concurrent_replicate_calls)

    async def process(self, *, jwt: str, user_id: str, item_id: str) -> None:
        """The full pipeline for one item. Never raises -- any failure along
        the way is caught and results in a ``bg_pending`` status update
        rather than an unhandled background-task exception."""
        image_key = original_image_key(user_id, item_id)

        try:
            original_bytes = await asyncio.to_thread(self._storage.get_object_bytes, image_key)
        except Exception as exc:  # noqa: BLE001 - background task, must not raise
            logger.warning(
                "bg_removal_original_read_failed",
                extra={"user_id": user_id, "item_id": item_id, "error": str(exc)},
            )
            await self._mark_pending(
                jwt=jwt, item_id=item_id, source="r2_read_failed", latency_ms=None
            )
            return

        if looks_already_transparent_or_white(original_bytes):
            await self._finish_success(
                jwt=jwt,
                user_id=user_id,
                item_id=item_id,
                clean_bytes=original_bytes,
                source="skipped_already_transparent",
                low_confidence=False,
                latency_ms=None,
            )
            return

        if await self._circuit_breaker.is_open():
            await self._mark_pending(
                jwt=jwt, item_id=item_id, source="circuit_open", latency_ms=None
            )
            return

        # Post-QA amendment (2026-07-25): the Replicate call itself gets a
        # smaller, in-memory-only proxy image, not the full-resolution
        # original -- see image_processing.resize_for_bg_removal and the
        # design doc's "Image sizing strategy" section. SS-010's original
        # stays untouched in R2.
        proxy_bytes = resize_for_bg_removal(original_bytes)

        async with self._semaphore:
            result = await self._provider.remove_background(proxy_bytes)

        if not result.success:
            await self._circuit_breaker.record_failure()
            await self._mark_pending(
                jwt=jwt, item_id=item_id, source="replicate_failed", latency_ms=result.latency_ms
            )
            return

        await self._circuit_breaker.record_success()
        assert (
            result.image_bytes is not None
        )  # success=True guarantees this per the port's contract

        logger.info(
            "ai_call",
            extra={
                "user_id": user_id,
                "cost_usd": COST_USD_PER_RUN,
                "latency_ms": result.latency_ms,
            },
        )

        # foreground_ratio/is_low_confidence run against Replicate's raw
        # (proxy-resolution) output -- scale-invariant, cheaper than running
        # it post-composite. The stored clean.png itself is composited back
        # onto the full-resolution original below.
        clean_bytes = apply_alpha_mask_to_original(original_bytes, result.image_bytes)

        await self._finish_success(
            jwt=jwt,
            user_id=user_id,
            item_id=item_id,
            clean_bytes=clean_bytes,
            source="replicate",
            low_confidence=is_low_confidence(result.image_bytes),
            latency_ms=result.latency_ms,
        )

    async def _finish_success(
        self,
        *,
        jwt: str,
        user_id: str,
        item_id: str,
        clean_bytes: bytes,
        source: str,
        low_confidence: bool,
        latency_ms: int | None,
    ) -> None:
        thumbnail_bytes = generate_thumbnail(clean_bytes)
        clean_key = clean_image_key(user_id, item_id)
        thumbnail_key = thumbnail_image_key(user_id, item_id)

        try:
            await asyncio.to_thread(
                self._storage.put_object_bytes, clean_key, clean_bytes, "image/png"
            )
            await asyncio.to_thread(
                self._storage.put_object_bytes, thumbnail_key, thumbnail_bytes, "image/jpeg"
            )
        except Exception as exc:  # noqa: BLE001 - background task, must not raise
            logger.warning(
                "bg_removal_r2_write_failed",
                extra={"item_id": item_id, "error": str(exc)},
            )
            await self._mark_pending(jwt=jwt, item_id=item_id, source=source, latency_ms=latency_ms)
            return

        await self._repository.update_bg_removal_result(
            jwt=jwt,
            item_id=item_id,
            processing_status="bg_removed",
            image_clean_url=clean_key,
            thumbnail_url=thumbnail_key,
            bg_removal_tags=_bg_removal_tags(source, low_confidence, latency_ms),
        )

    async def _mark_pending(
        self, *, jwt: str, item_id: str, source: str, latency_ms: int | None
    ) -> None:
        await self._repository.update_bg_removal_result(
            jwt=jwt,
            item_id=item_id,
            processing_status="bg_pending",
            image_clean_url=None,
            thumbnail_url=None,
            bg_removal_tags=_bg_removal_tags(source, False, latency_ms),
        )


def _bg_removal_tags(source: str, low_confidence: bool, latency_ms: int | None) -> dict[str, Any]:
    return {"source": source, "low_confidence": low_confidence, "latency_ms": latency_ms}
