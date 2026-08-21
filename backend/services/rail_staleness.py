"""SS-048 -- ``maybe_trigger_rail_recompute``: the debounce check every
wardrobe-write call site awaits directly (``routers/wardrobe.py``'s ``/tag``
and ``DELETE /items/{id}``, ``routers/outfit_suggestions.py``'s ``/outcome``
for ``saved``/``worn``).

Reads ``RAIL_PRECOMPUTE_DEBOUNCE_SPEC`` off the caller's own
``AppConfigSnapshot`` (one snapshot per request, per ``dependencies
.app_config``'s established contract), reads
``ISuggestionRailsRepository.get_most_recent_computed_at``, and -- only if
that value is ``None`` or older than the debounce window -- schedules
``RailPrecomputeService.recompute_all_rails`` via the caller-supplied
``BackgroundTasks``. Called directly (awaited) from inside the request
handler, not itself dispatched as a background task -- registering the
recompute task AFTER the router's own write-triggering background task
(e.g. ``service.tag``) is what makes the recompute run "on completion" of
that write: ``BackgroundTasks`` executes its tasks sequentially, in
registration order.

Wrapped in its own ``try/except`` (logs and swallows) -- a failed staleness
check must NEVER fail the wardrobe write it's attached to, same defensive
posture as ``EngineV2._log_session``/``OutfitPortfolioService._resolve_weather``.
Worst case on a swallowed failure: a recompute is skipped this cycle: the
next write's check catches it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks

from adapters.interfaces import ISuggestionRailsRepository
from services.app_config import AppConfigService, AppConfigSnapshot
from services.app_config_specs import RAIL_PRECOMPUTE_DEBOUNCE_SPEC
from services.rail_precompute_service import RailPrecomputeService

logger = logging.getLogger(__name__)


async def maybe_trigger_rail_recompute(
    *,
    jwt: str,
    user_id: str,
    background_tasks: BackgroundTasks,
    rails_repo: ISuggestionRailsRepository,
    rail_precompute_service: RailPrecomputeService,
    config_snapshot: AppConfigSnapshot,
    app_config: AppConfigService,
) -> None:
    try:
        debounce = app_config.read(config_snapshot, RAIL_PRECOMPUTE_DEBOUNCE_SPEC)
        most_recent = await rails_repo.get_most_recent_computed_at(jwt=jwt, user_id=user_id)

        is_stale = most_recent is None or (
            datetime.now(UTC) - most_recent >= timedelta(seconds=debounce.seconds)
        )
        if not is_stale:
            return

        background_tasks.add_task(
            rail_precompute_service.recompute_all_rails, jwt=jwt, user_id=user_id
        )
    except Exception as exc:  # noqa: BLE001 -- must never fail the wardrobe write it's attached to
        logger.warning(
            "rail_staleness_check_failed",
            extra={"user_id": user_id, "error": str(exc)},
        )
