"""``POST /wardrobe/remove-bg`` (SS-011) -- takes an already-uploaded (SS-010)
wardrobe photo through Replicate BRIA-RMBG background removal, behind a real
per-user daily rate limit and a circuit breaker.

This is also the first endpoint to ever create a ``wardrobe_items`` row
(SS-010 deliberately created none -- upload is R2-only). The row's ``id`` is
set to the client-supplied ``item_id`` (the same UUID SS-010's
``get-upload-url`` Edge Function returned), honoring that hand-off contract,
overriding the column's ``DEFAULT gen_random_uuid()``.

Row creation happens synchronously, after auth + rate-limit checks pass and
*before* the ``202`` response is returned -- so a client that immediately
subscribes to Supabase Realtime on ``id=eq.{item_id}`` finds the row already
there. The heavy work (Replicate call, R2 writes, subsequent updates) is
dispatched via ``BackgroundTasks.add_task`` (CLAUDE.md: "never call AI APIs
synchronously").
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator

from adapters.interfaces import IOccasionRepository, IWardrobeRepository
from adapters.occasion_repository import SupabaseOccasionRepository
from adapters.r2_storage import R2StorageClient
from adapters.wardrobe_repository import SupabaseWardrobeRepository
from ai.adapters.gemini_vision_adapter import GeminiVisionAdapter
from ai.adapters.replicate_bg_removal_adapter import ReplicateBgRemovalAdapter
from ai.ports.interfaces import IBackgroundRemovalProvider, IVisionProvider
from dependencies.app_config import get_app_config_snapshot
from dependencies.auth import get_current_user_id
from services.app_config import AppConfigSnapshot, app_config_service
from services.app_config_specs import GEMINI_QUOTA_CEILING_SPEC
from services.circuit_breaker import CircuitBreaker
from services.gemini_rate_limiter import GeminiRateLimiter
from services.occasion_normalizer import OccasionNormalizer
from services.rate_limiter import DailyRateLimiter
from services.tag_cache import TagCache
from services.wardrobe_bg_removal_service import WardrobeBgRemovalService
from services.wardrobe_deletion_service import WardrobeDeletionService
from services.wardrobe_tagging_service import WardrobeTaggingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])

_PREMIUM_PLAN_TIERS = {"premium", "premium_annual"}
_FREE_DAILY_LIMIT = 20

# SS-012: GeminiRateLimiter holds real in-process state (a sliding-window
# deque of call timestamps) that must be shared across requests to mean
# anything -- unlike CircuitBreaker/DailyRateLimiter/TagCache below, whose
# state lives in Upstash Redis, so a fresh wrapper instance per request is
# harmless for those. A fresh GeminiRateLimiter() per request would never
# remember any prior call and would make the 15 RPM gate a no-op. Built
# once at import time; still swappable via dependency_overrides for tests.
_gemini_rate_limiter = GeminiRateLimiter()

# (SS-025) Process-wide, for the same reason as _gemini_rate_limiter: its 60s
# TTL registry cache only pays for itself across requests. Holds no caller
# credentials -- the JWT is a per-call argument.
_occasion_normalizer = OccasionNormalizer(SupabaseOccasionRepository())


def _safe_bearer_token(authorization: str | None) -> str | None:
    """Like _extract_bearer_token below, but returns None instead of raising
    on a missing/malformed header. Used only where the token is an OPTIONAL
    enrichment (rendering the occasion vocabulary into the Gemini prompt) --
    a DI provider must not be the thing that 401s a request; the route's own
    auth dependency owns that."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer ") :].strip() or None


def get_background_removal_provider() -> IBackgroundRemovalProvider:
    """The binding from port to concrete adapter lives here, and only here --
    the route handler never imports ReplicateBgRemovalAdapter directly.
    Override via app.dependency_overrides to swap in a fake for tests."""
    return ReplicateBgRemovalAdapter()


def get_wardrobe_repository() -> IWardrobeRepository:
    return SupabaseWardrobeRepository()


def get_r2_storage_client() -> R2StorageClient:
    return R2StorageClient()


def get_circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker()


def get_daily_rate_limiter() -> DailyRateLimiter:
    return DailyRateLimiter(max_requests=_FREE_DAILY_LIMIT)


def get_bg_removal_service(
    provider: IBackgroundRemovalProvider = Depends(get_background_removal_provider),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    storage: R2StorageClient = Depends(get_r2_storage_client),
    circuit_breaker: CircuitBreaker = Depends(get_circuit_breaker),
) -> WardrobeBgRemovalService:
    return WardrobeBgRemovalService(provider, repository, storage, circuit_breaker)


def get_occasion_repository() -> IOccasionRepository:
    """(SS-025) Port -> adapter binding for the occasion registry. Route
    handlers depend on the port, never on SupabaseOccasionRepository."""
    return SupabaseOccasionRepository()


def get_occasion_normalizer() -> OccasionNormalizer:
    """Returns the process-wide singleton, NOT a per-request instance -- the
    60s TTL registry cache only pays for itself if it survives across
    requests (same reasoning as _gemini_rate_limiter above). The caller's JWT
    is passed per call, not held, so the singleton never carries one user's
    credentials into another user's request."""
    return _occasion_normalizer


def get_vision_provider(
    authorization: str | None = Header(default=None),
    occasion_normalizer: OccasionNormalizer = Depends(get_occasion_normalizer),
) -> IVisionProvider:
    """The binding from port to concrete adapter lives here, and only here
    -- the route handler never imports GeminiVisionAdapter directly.
    Override via app.dependency_overrides to swap in a fake for tests.

    (SS-025) The normaliser and the caller's JWT are constructor-injected so
    the adapter can render the occasion vocabulary from the live registry.
    IVisionProvider.tag_garment's signature is untouched (Open/Closed)."""
    return GeminiVisionAdapter(
        occasion_normalizer=occasion_normalizer,
        registry_jwt=_safe_bearer_token(authorization),
    )


def get_tag_cache() -> TagCache:
    return TagCache()


async def get_gemini_rate_limiter(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
) -> GeminiRateLimiter:
    """(SS-028, closes ``BL-076``) Reads ``gemini_quota_ceiling_rpm`` off
    ONE ``AppConfigSnapshot`` per request and applies it onto the SAME
    process-wide singleton via ``set_max_requests()`` -- the sliding-window
    state itself (``_timestamps``) must survive across requests to mean
    anything (see ``_gemini_rate_limiter``'s own comment above), so this
    still returns that one shared instance, never a fresh one. Zero I/O at
    import still holds -- the only I/O is the snapshot read the route
    already triggers via its other dependencies."""
    ceiling = app_config_service.read(snapshot, GEMINI_QUOTA_CEILING_SPEC)
    _gemini_rate_limiter.set_max_requests(ceiling.rpm)
    return _gemini_rate_limiter


def get_deletion_service(
    storage: R2StorageClient = Depends(get_r2_storage_client),
) -> WardrobeDeletionService:
    return WardrobeDeletionService(storage)


def get_tagging_service(
    provider: IVisionProvider = Depends(get_vision_provider),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    storage: R2StorageClient = Depends(get_r2_storage_client),
    cache: TagCache = Depends(get_tag_cache),
    rate_limiter: GeminiRateLimiter = Depends(get_gemini_rate_limiter),
    occasion_normalizer: OccasionNormalizer = Depends(get_occasion_normalizer),
) -> WardrobeTaggingService:
    return WardrobeTaggingService(
        provider, repository, storage, cache, rate_limiter, occasion_normalizer
    )


class RemoveBgRequest(BaseModel):
    item_id: str

    @field_validator("item_id")
    @classmethod
    def _item_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("item_id must be a valid UUID") from exc
        return value


# SS-013: GET /wardrobe/items/{id}/image-url -- short-lived presigned GET,
# same expiry window as SS-010's presigned PUT (PRESIGNED_URL_EXPIRY_SECONDS)
# rather than inventing a new value.
_IMAGE_URL_EXPIRY_SECONDS = 300


class ImageUrlResponse(BaseModel):
    url: str
    source: Literal["clean", "original"]


# SS-014: POST /wardrobe/items/image-urls -- bulk resolution for the grid
# (see docs/tickets/SS-014-design.md's "Bulk image-URL endpoint contract").
# 1-200 ids per call: the free tier caps a wardrobe at 50 items and even a
# generous premium wardrobe fits comfortably under 200 (flagged, not fixed,
# as a real-if-unlikely-pre-launch gap in the design doc's Edge Cases).
_BULK_IMAGE_URLS_MIN_ITEMS = 1
_BULK_IMAGE_URLS_MAX_ITEMS = 200


class BulkImageUrlsRequest(BaseModel):
    item_ids: list[str]

    @field_validator("item_ids")
    @classmethod
    def _item_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        if not (_BULK_IMAGE_URLS_MIN_ITEMS <= len(value) <= _BULK_IMAGE_URLS_MAX_ITEMS):
            raise ValueError(
                f"item_ids must contain between {_BULK_IMAGE_URLS_MIN_ITEMS} and "
                f"{_BULK_IMAGE_URLS_MAX_ITEMS} items"
            )
        for item_id in value:
            try:
                uuid.UUID(item_id)
            except ValueError as exc:
                raise ValueError(f"{item_id} is not a valid UUID") from exc
        return value


class ImageUrlInfo(BaseModel):
    url: str
    source: Literal["thumbnail", "original"]


class BulkImageUrlsResponse(BaseModel):
    urls: dict[str, ImageUrlInfo]


class TagRequest(BaseModel):
    item_id: str

    # Reuses RemoveBgRequest's own UUID field_validator pattern verbatim
    # (SS-012 design doc's Endpoint contract) -- malformed UUID -> 422, not
    # 500.
    @field_validator("item_id")
    @classmethod
    def _item_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("item_id must be a valid UUID") from exc
        return value


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return authorization[len("Bearer ") :].strip()


@router.post("/remove-bg", status_code=202)
async def remove_background(
    request: RemoveBgRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    user_id: str = Depends(get_current_user_id),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    rate_limiter: DailyRateLimiter = Depends(get_daily_rate_limiter),
    service: WardrobeBgRemovalService = Depends(get_bg_removal_service),
) -> dict[str, Any]:
    jwt = _extract_bearer_token(authorization)

    try:
        plan_tier = await repository.get_plan_tier(jwt=jwt, user_id=user_id)
        is_premium = plan_tier in _PREMIUM_PLAN_TIERS

        allowed = await rate_limiter.check_and_increment(user_id, skip=is_premium)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Daily background-removal limit reached. Upgrade to premium for unlimited use.",
            )

        image_key = f"wardrobe/{user_id}/{request.item_id}/original.jpg"
        await repository.upsert_uploaded_row(
            jwt=jwt, item_id=request.item_id, user_id=user_id, image_key=image_key
        )

        background_tasks.add_task(
            service.process, jwt=jwt, user_id=user_id, item_id=request.item_id
        )

        return {"status": "processing", "item_id": request.item_id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("wardrobe_remove_bg_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to start background removal") from exc


@router.post("/tag", status_code=202)
async def tag_wardrobe_item(
    request: TagRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    user_id: str = Depends(get_current_user_id),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    service: WardrobeTaggingService = Depends(get_tagging_service),
) -> dict[str, Any]:
    jwt = _extract_bearer_token(authorization)

    try:
        exists = await repository.item_exists(jwt=jwt, item_id=request.item_id)
        if not exists:
            raise HTTPException(
                status_code=404,
                detail="Wardrobe item not found. Call /wardrobe/remove-bg first.",
            )

        background_tasks.add_task(service.tag, jwt=jwt, user_id=user_id, item_id=request.item_id)

        return {"status": "processing", "item_id": request.item_id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("wardrobe_tag_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to start tagging") from exc


@router.get("/items/{item_id}/image-url", response_model=ImageUrlResponse)
async def get_item_image_url(
    item_id: str,
    authorization: str | None = Header(default=None),
    user_id: str = Depends(get_current_user_id),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    storage: R2StorageClient = Depends(get_r2_storage_client),
) -> ImageUrlResponse:
    """SS-013 (BL-046 read path, authorized 2026-07-25 -- see
    docs/tickets/SS-013-design.md's Open questions #1). Returns a fresh
    short-lived presigned GET for the item's `clean.png`, falling back to
    `original.jpg` when `processing_status` never reached `bg_removed`
    (BG-removal failed/pending doesn't block reviewing/tagging the item --
    the two pipelines are independent per SS-012's own design)."""
    jwt = _extract_bearer_token(authorization)

    try:
        uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="item_id must be a valid UUID") from exc

    try:
        info = await repository.get_item_image_info(jwt=jwt, item_id=item_id)
        if info is None:
            # Covers both "doesn't exist" and "not owned by this user" (RLS
            # already filtered the latter out) -- deliberately the same 404,
            # not an ownership oracle.
            raise HTTPException(status_code=404, detail="Wardrobe item not found")

        processing_status = info.get("processing_status")
        image_clean_url = info.get("image_clean_url")
        image_url = info.get("image_url")

        if processing_status == "bg_removed" and image_clean_url:
            key = image_clean_url
            source: Literal["clean", "original"] = "clean"
        elif image_url:
            key = image_url
            source = "original"
        else:
            raise HTTPException(status_code=404, detail="Wardrobe item has no image yet")

        url = storage.generate_presigned_get_url(key, _IMAGE_URL_EXPIRY_SECONDS)
        return ImageUrlResponse(url=url, source=source)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("wardrobe_image_url_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to generate image URL") from exc


@router.post("/items/image-urls", response_model=BulkImageUrlsResponse)
async def get_bulk_item_image_urls(
    request: BulkImageUrlsRequest,
    authorization: str | None = Header(default=None),
    user_id: str = Depends(get_current_user_id),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    storage: R2StorageClient = Depends(get_r2_storage_client),
) -> BulkImageUrlsResponse:
    """SS-014 (grid-scale thumbnail resolution -- see
    docs/tickets/SS-014-design.md's "Bulk image-URL endpoint contract").
    Per id: thumbnail_url present -> source='thumbnail'; else image_url
    present -> source='original'; else the id is silently omitted from the
    response map (not a per-id error -- RLS already filters out ids the
    caller doesn't own, mirroring the single-item endpoint's "not an
    ownership oracle" precedent)."""
    jwt = _extract_bearer_token(authorization)

    try:
        info_map = await repository.get_items_image_info_bulk(jwt=jwt, item_ids=request.item_ids)

        urls: dict[str, ImageUrlInfo] = {}
        for item_id, info in info_map.items():
            thumbnail_url = info.get("thumbnail_url")
            image_url = info.get("image_url")
            if thumbnail_url:
                key = thumbnail_url
                source: Literal["thumbnail", "original"] = "thumbnail"
            elif image_url:
                key = image_url
                source = "original"
            else:
                continue
            urls[item_id] = ImageUrlInfo(
                url=storage.generate_presigned_get_url(key, _IMAGE_URL_EXPIRY_SECONDS),
                source=source,
            )

        return BulkImageUrlsResponse(urls=urls)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("wardrobe_bulk_image_urls_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to generate image URLs") from exc


@router.delete("/items/{item_id}")
async def delete_wardrobe_item(
    item_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    user_id: str = Depends(get_current_user_id),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    deletion_service: WardrobeDeletionService = Depends(get_deletion_service),
) -> dict[str, Any]:
    """SS-015 (resolves BL-068). Captures the item's three R2 keys *before*
    deleting the DB row, then deletes the row, then fires the storage
    cleanup asynchronously via BackgroundTasks -- in that order (DB row
    first, storage second), so a request that dies partway through never
    leaves an item that survives with its images gone. ON DELETE CASCADE on
    wardrobe_item_wears' composite FK removes that item's wear-history rows
    as part of the same DB delete."""
    jwt = _extract_bearer_token(authorization)

    try:
        uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="item_id must be a valid UUID") from exc

    try:
        info = await repository.get_item_image_info(jwt=jwt, item_id=item_id)
        if info is None:
            # Covers both "doesn't exist" and "not owned by this user" --
            # same not-an-ownership-oracle posture as get_item_image_url.
            raise HTTPException(status_code=404, detail="Wardrobe item not found")

        deleted = await repository.delete_item(jwt=jwt, item_id=item_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Wardrobe item not found")

        keys = [
            key
            for key in (
                info.get("image_url"),
                info.get("image_clean_url"),
                info.get("thumbnail_url"),
            )
            if key
        ]
        background_tasks.add_task(
            deletion_service.cleanup_storage, user_id=user_id, item_id=item_id, keys=keys
        )

        return {"status": "deleted", "item_id": item_id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("wardrobe_item_delete_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to delete wardrobe item") from exc
