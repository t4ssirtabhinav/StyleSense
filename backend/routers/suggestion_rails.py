"""SS-048 -- ``GET /suggestion-rails`` / ``POST /suggestion-rails/refresh``.

``GET`` is a PURE READ: one indexed query against ``suggestion_rails``, no
side effects, no ``BackgroundTasks`` triggered here (the AC's "on wardrobe
write" / "on demand" trigger list deliberately does not include a plain
read -- see design doc's Edge cases). A rail with an empty/missing payload
is OMITTED from the response array entirely -- ``SS-049``'s mobile consumer
renders exactly what it receives, no empty-state branching of its own.

``POST /refresh`` is synchronous, awaited -- mirrors ``OutfitPortfolioService``'s
own "awaited synchronously inside the request handler, explicit user
action" precedent (``SS-020``'s signed-off Open Question #1) -- calls
``RailPrecomputeService.recompute_all_rails`` directly, then returns the
freshly-written rows in the same shape as ``GET``.

Same auth pattern as ``outfit_suggestions.py``'s ``/portfolio``/``/outcome``:
the REAL, signature-verified ``dependencies.auth.get_current_user_id`` +
``_extract_bearer_token`` for the RLS-scoped repository calls.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from adapters.interfaces import ISuggestionRailsRepository, SuggestionRailRow
from adapters.occasion_repository import SupabaseOccasionRepository
from adapters.outfit_repository import SupabaseOutfitRepository
from adapters.suggestion_rails_repository import SupabaseSuggestionRailsRepository
from adapters.wardrobe_repository import SupabaseWardrobeRepository
from dependencies.auth import get_current_user_id
from services.engine_v2 import build_default_engine_v2
from services.garment_registry_adapter import garment_registry_adapter
from services.occasion_normalizer import OccasionNormalizer
from services.rail_precompute_service import RailPrecomputeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suggestion-rails", tags=["suggestion-rails"])

# Process-wide singletons -- same "zero I/O at construction, real
# in-process state (registry/config caches) that only pays for itself
# across requests" reasoning as routers/outfit_suggestions.py's own module-
# level singletons. Each router builds its own repository instances (no
# shared mutable state with outfit_suggestions.py); garment_registry_adapter
# is the one exception, reused deliberately (see build_default_engine_v2's
# own docstring) -- its TTL cache is harmless to share and refresh() is
# idempotent within the TTL window.
_wardrobe_repository = SupabaseWardrobeRepository()
_outfit_repository = SupabaseOutfitRepository()
_rails_repository = SupabaseSuggestionRailsRepository()
_occasion_normalizer = OccasionNormalizer(SupabaseOccasionRepository())
_engine_v2 = build_default_engine_v2()
_rail_precompute_service = RailPrecomputeService(
    engine=_engine_v2,
    wardrobe_repo=_wardrobe_repository,
    outfit_repo=_outfit_repository,
    garment_registry=garment_registry_adapter,
    rails_repo=_rails_repository,
    occasion_normalizer=_occasion_normalizer,
)


def get_rails_repository() -> ISuggestionRailsRepository:
    return _rails_repository


def get_rail_precompute_service() -> RailPrecomputeService:
    return _rail_precompute_service


def _extract_bearer_token(authorization: str | None) -> str:
    """Mirrors routers/wardrobe.py's/outfit_suggestions.py's own helper --
    get_current_user_id already validated the header shape/signature, this
    just re-extracts the raw token string for RLS-scoped repository calls."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


class RailDisplayItemResponse(BaseModel):
    """One item's compute-time display snapshot -- mirrors
    ``outfits.items_snapshot``'s own denormalisation shape (see
    ``rail_precompute_service.py``'s module docstring)."""

    item_id: str
    category: str | None = None
    color_primary: str | None = None
    thumbnail_url: str | None = None


class RailPayloadItemResponse(BaseModel):
    """One payload entry within a rail: a whole outfit (``todays_picks``/
    ``newest_pieces``, ``outfit_fingerprint``/``total_score`` present) or a
    pair/single item (``never_tried_pairs``/``not_yet_worn``, those two
    fields absent -- no engine involvement)."""

    item_ids: list[str]
    items: list[RailDisplayItemResponse]
    outfit_fingerprint: str | None = None
    total_score: float | None = None


class SuggestionRailResponse(BaseModel):
    rail_key: str
    computed_at: str
    engine_version: str | None
    items: list[RailPayloadItemResponse]


class SuggestionRailsResponse(BaseModel):
    rails: list[SuggestionRailResponse]


def _build_rails_response(rows: list[SuggestionRailRow]) -> SuggestionRailsResponse:
    """A rail whose payload has 0 items is OMITTED entirely -- design doc's
    Router contract."""
    entries: list[SuggestionRailResponse] = []
    for row in rows:
        items = row.payload.get("items") if isinstance(row.payload, dict) else None
        if not items:
            continue
        entries.append(
            SuggestionRailResponse.model_validate(
                {
                    "rail_key": row.rail_key,
                    "computed_at": row.computed_at.isoformat(),
                    "engine_version": row.engine_version,
                    "items": items,
                }
            )
        )
    return SuggestionRailsResponse(rails=entries)


@router.get("", response_model=SuggestionRailsResponse)
async def get_suggestion_rails(
    user_id: str = Depends(get_current_user_id),
    authorization: str | None = Header(default=None),
    rails_repo: ISuggestionRailsRepository = Depends(get_rails_repository),
) -> SuggestionRailsResponse:
    """Pure read -- no side effects, no BackgroundTasks. A brand-new user
    with no rows at all gets ``{"rails": []}``, never a 404/500."""
    jwt_token = _extract_bearer_token(authorization)
    try:
        rows = await rails_repo.get_rails(jwt=jwt_token, user_id=user_id)
        return _build_rails_response(rows)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("suggestion_rails_get_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to load suggestion rails") from exc


@router.post("/refresh", response_model=SuggestionRailsResponse)
async def refresh_suggestion_rails(
    user_id: str = Depends(get_current_user_id),
    authorization: str | None = Header(default=None),
    rails_repo: ISuggestionRailsRepository = Depends(get_rails_repository),
    precompute_service: RailPrecomputeService = Depends(get_rail_precompute_service),
) -> SuggestionRailsResponse:
    """Synchronous, awaited -- explicit user action (design doc's Router
    contract, mirroring SS-020's own signed-off precedent)."""
    jwt_token = _extract_bearer_token(authorization)
    try:
        await precompute_service.recompute_all_rails(jwt=jwt_token, user_id=user_id)
        rows = await rails_repo.get_rails(jwt=jwt_token, user_id=user_id)
        return _build_rails_response(rows)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("suggestion_rails_refresh_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to refresh suggestion rails") from exc
