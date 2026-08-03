"""Stub endpoint proving the IStylingProvider -> OutfitSuggestionService ->
router wiring end-to-end (SS-006). Canned output only -- no real
personalization, no real auth, no real result-delivery mechanism yet (see
docs/tickets/SS-006-design.md's "Open questions").

(SS-028) ``get_styling_provider()`` now builds a ``StylingRouter`` per
request -- the composition root where the port swap the ticket's own
framing calls out actually happens ("the first real proof the ports
architecture pays for itself"). Every ``Depends()`` helper below ultimately
depends on ``get_app_config_snapshot`` (``dependencies/app_config.py``),
which FastAPI caches per request by default -- so exactly ONE
``AppConfigService.snapshot()`` call backs every read in a single request,
satisfying design §4.4/N2 by construction, not by convention.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel

from ai.adapters.styling_provider_registry import StylingProviderRegistry
from ai.ports.interfaces import IStylingProvider
from dependencies.app_config import get_app_config_snapshot
from services.ai_routing_specs import (
    AI_PROVIDER_QUOTA_SPEC,
    AI_ROUTER_POLICY_SPEC,
    AI_STYLING_ROUTING_TABLE_SPEC,
)
from services.app_config import AppConfigSnapshot, app_config_service
from services.outfit_suggestion_service import OutfitSuggestionService
from services.provider_quota import ProviderQuotaTracker
from services.routing_mix_monitor import RoutingMixMonitor
from services.styling_router import RoutingContext, StylingRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outfit-suggestions", tags=["outfit-suggestions"])

# Process-wide singletons -- same reasoning as routers/wardrobe.py's
# _gemini_rate_limiter/_occasion_normalizer: each holds real in-process
# state (a sliding-window quota reservation, a rolling routing-mix sample,
# a per-(provider,model) adapter cache) that only means anything if it
# survives across requests. Built with ZERO I/O at import (mirrors that
# same file's pattern exactly); still swappable via dependency_overrides
# for tests.
_provider_quota_tracker = ProviderQuotaTracker()
_routing_mix_monitor = RoutingMixMonitor()
_styling_provider_registry = StylingProviderRegistry()


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


def get_styling_provider_registry() -> StylingProviderRegistry:
    return _styling_provider_registry


def get_provider_quota_tracker(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
) -> ProviderQuotaTracker:
    quota_config = app_config_service.read(snapshot, AI_PROVIDER_QUOTA_SPEC)
    ceilings = {
        provider: (entry.rpm, entry.tpm) for provider, entry in quota_config.root.items()
    }
    _provider_quota_tracker.set_ceilings(ceilings)
    return _provider_quota_tracker


def get_routing_mix_monitor(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
) -> RoutingMixMonitor:
    policy = app_config_service.read(snapshot, AI_ROUTER_POLICY_SPEC)
    _routing_mix_monitor.configure(
        alert_min_sample=policy.alert_min_sample,
        expensive_share_alert_threshold=policy.expensive_share_alert_threshold,
        alert_cooldown_seconds=policy.alert_cooldown_seconds,
        provider_outage_alert_seconds=policy.provider_outage_alert_seconds,
    )
    return _routing_mix_monitor


def get_routing_context(user_id: str = Depends(get_current_user_id_stub)) -> RoutingContext:
    """(SS-028) Every field beyond ``user_id`` stays at its default (cheap/
    everyday route) until a real caller supplies tier/occasion/first-
    suggestion signals -- SS-020's job, not this ticket's (constraint §2.4:
    unknown context routes cheap, never "to be safe" expensive)."""
    return RoutingContext(user_id=user_id)


def get_styling_provider(
    snapshot: AppConfigSnapshot = Depends(get_app_config_snapshot),
    registry: StylingProviderRegistry = Depends(get_styling_provider_registry),
    quota: ProviderQuotaTracker = Depends(get_provider_quota_tracker),
    monitor: RoutingMixMonitor = Depends(get_routing_mix_monitor),
    context: RoutingContext = Depends(get_routing_context),
) -> IStylingProvider:
    """The binding from port to concrete adapter lives here, and only here --
    the route handler below never imports StylingRouter/MockStylingAdapter
    directly. Override this dependency (via app.dependency_overrides) to
    swap in a different IStylingProvider without touching this router file
    -- the exact seam SS-006 documented, still intact after SS-028.
    """
    routing_table = app_config_service.read(snapshot, AI_STYLING_ROUTING_TABLE_SPEC)
    policy = app_config_service.read(snapshot, AI_ROUTER_POLICY_SPEC)
    return StylingRouter(
        registry=registry,
        routing_table=routing_table,
        policy=policy,
        quota=quota,
        monitor=monitor,
        context=context,
        snapshot_stale=snapshot.stale,
    )


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
