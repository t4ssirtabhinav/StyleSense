"""Supabase-backed ``IGarmentRegistryRepository`` implementation (SS-038).

**Uses ``service_role``, not caller-JWT** -- deliberate, explicit deviation
from this file's siblings (``SupabaseWardrobeRepository``,
``SupabaseOccasionRepository``, ``SupabaseWearHistoryRepository``), same
justification as ``IAppConfigRepository``'s own documented precedent
(``app_config_repository.py``'s module docstring): ``garment_types`` is
non-user-owned reference data, its RLS policy (``authenticated_read_garment_types``,
``014_garment_types_registry.sql``) requires only ``auth.role() =
'authenticated'`` (no per-user ownership), and the hot scoring loop needs
``GarmentRegistryAdapter.get_garment_attributes`` callable with NO jwt in
hand (per the ticket's own literal signature). Documented here rather than
silently introduced, per ``app_config_repository.py``'s own stated norm.

**Flagged for Developer/QA double-check (design doc's own "Open questions"
#3):** this is convenience, not strict necessity -- ``IOccasionRepository``
uses caller-JWT scoping for a structurally IDENTICAL RLS shape
(``authenticated``-only, no ownership). If a future reviewer prefers
caller-JWT scoping here too, that is a valid alternative; this repository
uses ``service_role`` because ``get_garment_attributes(category: str)``'s
literal signature carries no ``jwt`` parameter.
"""

from __future__ import annotations

import os
from typing import Any, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import GarmentRegistrySnapshot, GarmentTypeRow, IGarmentRegistryRepository


async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    # SERVICE_ROLE, not anon+JWT -- see module docstring for why this is a
    # deliberate exception to this file's siblings' convention.
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)


def _to_row(raw: dict[str, Any]) -> GarmentTypeRow:
    return GarmentTypeRow(
        key=str(raw["key"]),
        slot=str(raw["slot"]),
        layer=int(raw["layer"]),
        register=tuple(raw.get("register") or ()),
        base_formality=int(raw["base_formality"]),
        pairs_with=tuple(raw.get("pairs_with") or ()),
        requires_with=tuple(raw.get("requires_with") or ()),
        excludes_with=tuple(raw.get("excludes_with") or ()),
        styling_rules=cast(dict[str, Any], raw.get("styling_rules") or {}),
    )


class SupabaseGarmentRegistryRepository(IGarmentRegistryRepository):
    """Real DB access for ``garment_types``/``garment_type_aliases``.
    Constructor-injected into ``GarmentRegistryAdapter`` behind the
    ``IGarmentRegistryRepository`` port."""

    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        client = await _client()
        types_response = (
            await client.table("garment_types")
            .select(
                "key, slot, layer, register, base_formality, pairs_with, "
                "requires_with, excludes_with, styling_rules"
            )
            .eq("is_active", True)
            .execute()
        )
        aliases_response = (
            await client.table("garment_type_aliases").select("alias, garment_key").execute()
        )

        type_rows = cast(list[dict[str, Any]], types_response.data or [])
        rows = {row.key: row for row in (_to_row(raw) for raw in type_rows)}

        alias_rows = cast(list[dict[str, Any]], aliases_response.data or [])
        aliases = {str(row["alias"]): str(row["garment_key"]) for row in alias_rows}

        return GarmentRegistrySnapshot(rows=rows, aliases=aliases)
