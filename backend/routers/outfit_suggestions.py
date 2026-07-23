"""Stub endpoint proving the IStylingProvider -> OutfitSuggestionService ->
router wiring end-to-end (SS-006). Canned output only -- no real
personalization, no real auth, no real result-delivery mechanism yet (see
docs/tickets/SS-006-design.md's "Open questions").
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel

from ai.adapters.mock_styling_adapter import MockStylingAdapter
from ai.ports.interfaces import IStylingProvider
from services.outfit_suggestion_service import OutfitSuggestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outfit-suggestions", tags=["outfit-suggestions"])


def get_current_user_id_stub(authorization: str | None = Header(default=None)) -> str:
    """NON-PRODUCTION STUB. Reads the JWT payload's `sub` claim WITHOUT
    verifying the token's signature. This is UNSAFE for real traffic --
    acceptable only because nothing behind this router is real (mock
    adapter, no writes, no sensitive reads, no deployed caller yet).

    Before any real traffic reaches this or any future backend endpoint, a
    proper Supabase JWT-verification dependency must replace this. Logged
    as BL-033 (Active, tag `auth`) -- do not treat this as real auth.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Malformed or non-JWT-shaped token") from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")

    return str(sub)


def get_styling_provider() -> IStylingProvider:
    """The binding from port to concrete adapter lives here, and only here --
    the route handler below never imports MockStylingAdapter directly.
    Override this dependency (via app.dependency_overrides) to swap in a
    different IStylingProvider without touching this router file.
    """
    return MockStylingAdapter()


def get_outfit_suggestion_service(
    provider: IStylingProvider = Depends(get_styling_provider),
) -> OutfitSuggestionService:
    return OutfitSuggestionService(provider)


class GenerateSuggestionsRequest(BaseModel):
    """Raw, unvalidated style_preferences payload -- mirrors the nullable
    JSONB shape of users.style_preferences. Validated/normalized inside
    OutfitSuggestionService, not here (single source of truth for the
    null/partial/malformed degrade path)."""

    style_preferences: dict[str, Any] | None = None


@router.post("/generate", status_code=202)
async def generate_outfit_suggestions(
    background_tasks: BackgroundTasks,
    request: GenerateSuggestionsRequest | None = None,
    user_id: str = Depends(get_current_user_id_stub),
    service: OutfitSuggestionService = Depends(get_outfit_suggestion_service),
) -> dict[str, Any]:
    try:
        raw_preferences = request.style_preferences if request else None
        background_tasks.add_task(service.generate_suggestions, user_id, raw_preferences)
        return {"status": "queued", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("outfit_suggestions_generate_failed", extra={"user_id": user_id})
        raise HTTPException(status_code=500, detail="Failed to queue outfit suggestion generation") from exc
