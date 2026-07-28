"""Best-effort R2 cleanup for a deleted wardrobe item (SS-015, resolves
``BL-068``).

Single-responsibility service, dispatched via ``BackgroundTasks`` *after*
the DB row has already been deleted (see ``routers/wardrobe.py``'s
``DELETE /wardrobe/items/{item_id}`` -- DB row first, storage second, so an
item never survives with its images gone). A failed cleanup here must never
surface as an error to a user whose item is already gone -- caught, logged,
and swallowed (``BL-074``: this is best-effort, no retry/sweeper).
"""

from __future__ import annotations

import asyncio
import logging

from adapters.r2_storage import R2StorageClient

logger = logging.getLogger(__name__)


class WardrobeDeletionService:
    def __init__(self, storage: R2StorageClient) -> None:
        self._storage = storage

    async def cleanup_storage(self, *, user_id: str, item_id: str, keys: list[str]) -> None:
        non_null_keys = [key for key in keys if key]
        if not non_null_keys:
            return
        try:
            await asyncio.to_thread(self._storage.delete_objects, non_null_keys)
        except Exception:  # noqa: BLE001 - background task, must not raise
            logger.exception(
                "wardrobe_item_delete_storage_cleanup_failed",
                extra={"user_id": user_id, "item_id": item_id, "keys": non_null_keys},
            )
