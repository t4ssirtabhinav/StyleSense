"""SS-038 -- the cached ``garment_types`` lookup Engine v2's candidate
search/attribute scoring stages depend on.

TTL-cached, mirrors ``OccasionNormalizer.get_registry``/``AppConfigService.snapshot``'s
established precedent exactly: ``refresh()`` never raises, serves the last
successful snapshot (or an empty one if there has never been a successful
fetch) on a repository failure -- stale-or-empty-serving beats a hard
failure of the whole scoring pipeline over one registry read.

``get_garment_attributes`` is pure/sync given whatever is cached: normalizes
``category.strip().lower()``, checks ``snapshot.rows`` (exact key) FIRST,
then ``snapshot.aliases`` (alias -> key -> row) -- mirrors the SQL-side
normalisation function's (014's) step-2-before-step-3 resolution order,
WITHOUT writing to the SQL-side unknown-slug capture table (this is a
read-only hot-path consumer; logging every fallback category -- 100% of
them today, since no live ``wardrobe_items.category`` value resolves
through ``garment_types`` yet -- would spam that table for no review value,
see ``BL-132``).

Module-scope singleton, constructed with ZERO I/O -- mirrors
``app_config_service``'s precedent exactly.
"""

from __future__ import annotations

import logging
import time

from adapters.garment_registry_repository import SupabaseGarmentRegistryRepository
from adapters.interfaces import GarmentRegistrySnapshot, GarmentTypeRow, IGarmentRegistryRepository
from services.engine_v2_types import GarmentAttributes
from services.styling_rules_defaults import GARMENT_SLOT_TO_ASSEMBLY_SLOT

logger = logging.getLogger(__name__)

DEFAULT_GARMENT_REGISTRY_TTL_SECONDS = 60.0


def _to_garment_attributes(row: GarmentTypeRow) -> GarmentAttributes | None:
    """Never raises -- a data-shape surprise (an unrecognised ``slot`` value,
    a malformed ``styling_rules``) degrades to "unresolved" (``None``, the
    same outcome as no row at all) rather than crashing the hot scoring
    loop."""
    assembly_slot = GARMENT_SLOT_TO_ASSEMBLY_SLOT.get(row.slot)
    if assembly_slot is None:
        logger.warning("garment_registry_unknown_slot", extra={"key": row.key, "slot": row.slot})
        return None

    volume_class: str | None = None
    if isinstance(row.styling_rules, dict):
        raw_volume_class = row.styling_rules.get("volume_class")
        if isinstance(raw_volume_class, str):
            volume_class = raw_volume_class

    try:
        return GarmentAttributes(
            key=row.key,
            assembly_slot=assembly_slot,
            garment_slot=row.slot,  # type: ignore[arg-type]
            layer=row.layer,
            register=row.register,
            base_formality=row.base_formality,
            pairs_with=row.pairs_with,
            requires_with=row.requires_with,
            excludes_with=row.excludes_with,
            volume_class=volume_class,
        )
    except Exception as exc:  # noqa: BLE001 -- never break the hot scoring loop over one bad row
        logger.warning(
            "garment_registry_row_invalid", extra={"key": row.key, "error": str(exc)}
        )
        return None


class GarmentRegistryAdapter:
    def __init__(
        self,
        repository: IGarmentRegistryRepository,
        *,
        ttl_seconds: float = DEFAULT_GARMENT_REGISTRY_TTL_SECONDS,
    ) -> None:
        self._repository = repository
        self._ttl_seconds = ttl_seconds
        self._snapshot: GarmentRegistrySnapshot | None = None
        self._fetched_at: float | None = None

    async def refresh(self) -> None:
        """Never raises. TTL-cached, safe to call every request. On a
        repository failure, keeps serving the last-good snapshot (or stays
        empty if there has never been a successful fetch) -- mirrors
        ``OccasionNormalizer.get_registry``."""
        now = time.monotonic()
        if (
            self._snapshot is not None
            and self._fetched_at is not None
            and (now - self._fetched_at) < self._ttl_seconds
        ):
            return
        try:
            snapshot = await self._repository.fetch_registry()
        except Exception as exc:  # noqa: BLE001 -- registry read must never break scoring
            logger.warning("garment_registry_fetch_failed", extra={"error": str(exc)})
            return
        self._snapshot = snapshot
        self._fetched_at = now

    def get_garment_attributes(self, category: str) -> GarmentAttributes | None:
        """Pure, sync, given whatever is cached. If ``refresh()`` was never
        awaited (a caller bug), ``_snapshot`` is still ``None`` -- every
        lookup returns ``None`` (full fallback), safe, not a crash."""
        if self._snapshot is None:
            return None
        normalized = category.strip().lower()
        row = self._snapshot.rows.get(normalized)
        if row is None:
            alias_target = self._snapshot.aliases.get(normalized)
            if alias_target is not None:
                row = self._snapshot.rows.get(alias_target)
        if row is None:
            return None
        return _to_garment_attributes(row)


# Module-scope singleton, constructed at import with ZERO I/O -- mirrors
# app_config_service's precedent exactly. Nothing calls .refresh() until a
# real consumer (engine_v2.py) actually needs a lookup.
garment_registry_adapter = GarmentRegistryAdapter(SupabaseGarmentRegistryRepository())
