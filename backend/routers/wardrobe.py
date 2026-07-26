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

from adapters.interfaces import IWardrobeRepository
from adapters.r2_storage import R2StorageClient
from adapters.wardrobe_repository import SupabaseWardrobeRepository
from ai.adapters.gemini_vision_adapter import GeminiVisionAdapter
from ai.adapters.replicate_bg_removal_adapter import ReplicateBgRemovalAdapter
from ai.ports.interfaces import IBackgroundRemovalProvider, IVisionProvider
from dependencies.auth import get_current_user_id
from services.circuit_breaker import CircuitBreaker
from services.gemini_rate_limiter import GeminiRateLimiter
from services.rate_limiter import DailyRateLimiter
from services.tag_cache import TagCache
from services.wardrobe_bg_removal_service import WardrobeBgRemovalService
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


def get_vision_provider() -> IVisionProvider:
    """The binding from port to concrete adapter lives here, and only here
    -- the route handler never imports GeminiVisionAdapter directly.
    Override via app.dependency_overrides to swap in a fake for tests."""
    return GeminiVisionAdapter()


def get_tag_cache() -> TagCache:
    return TagCache()


def get_gemini_rate_limiter() -> GeminiRateLimiter:
    return _gemini_rate_limiter


def get_tagging_service(
    provider: IVisionProvider = Depends(get_vision_provider),
    repository: IWardrobeRepository = Depends(get_wardrobe_repository),
    storage: R2StorageClient = Depends(get_r2_storage_client),
    cache: TagCache = Depends(get_tag_cache),
    rate_limiter: GeminiRateLimiter = Depends(get_gemini_rate_limiter),
) -> WardrobeTaggingService:
    return WardrobeTaggingService(provider, repository, storage, cache, rate_limiter)


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
