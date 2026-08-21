"""Supabase-backed ``IWardrobeRepository`` implementation (SS-011).

Every method constructs a fresh RLS-scoped async Supabase client per call,
authenticated with the **caller's own bearer token** (never
``service_role``) via ``postgrest.auth(jwt)`` -- so Postgres's own
``user_owns_wardrobe``/``user_owns_profile`` RLS policies (``auth.uid() =
user_id`` / ``auth.uid() = id``) are a real defense-in-depth backstop
against an application-layer bug passing the wrong ``user_id``, exactly
mirroring SS-010's established pattern for its own Edge Function.

Uses ``supabase-py``'s async client (``acreate_client``/``AsyncClient``)
rather than the sync one used by ``dependencies/auth.py`` -- these methods
are declared ``async`` on the ``IWardrobeRepository`` port and issue real
network I/O per call, so the async client avoids blocking the event loop
(unlike the auth dependency's single, already-`[trained-knowledge]`-flagged
sync ``auth.get_user()`` call).
"""

from __future__ import annotations

import os
from typing import Any, Literal, cast

from supabase import AsyncClient, acreate_client

from adapters.interfaces import IWardrobeRepository


async def _client_for(jwt: str) -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    client = await acreate_client(url, anon_key)
    client.postgrest.auth(jwt)
    return client


class SupabaseWardrobeRepository(IWardrobeRepository):
    """Real DB access for the BG-removal pipeline. Constructor-injected into
    ``WardrobeBgRemovalService`` behind the ``IWardrobeRepository`` port."""

    async def upsert_uploaded_row(
        self,
        *,
        jwt: str,
        item_id: str,
        user_id: str,
        image_key: str,
    ) -> None:
        client = await _client_for(jwt)
        await (
            client.table("wardrobe_items")
            .upsert(
                {
                    "id": item_id,
                    "user_id": user_id,
                    "image_url": image_key,
                    "category": None,
                    "processing_status": "uploaded",
                },
                ignore_duplicates=True,
                on_conflict="id",
            )
            .execute()
        )

    async def update_bg_removal_result(
        self,
        *,
        jwt: str,
        item_id: str,
        processing_status: Literal["bg_removed", "bg_pending"],
        image_clean_url: str | None,
        thumbnail_url: str | None,
        bg_removal_tags: dict[str, Any],
    ) -> None:
        client = await _client_for(jwt)

        existing = (
            await client.table("wardrobe_items")
            .select("ai_tags")
            .eq("id", item_id)
            .limit(1)
            .execute()
        )
        existing_ai_tags: dict[str, Any] = {}
        if existing.data:
            existing_row = cast(dict[str, Any], existing.data[0])
            existing_ai_tags = dict(existing_row.get("ai_tags") or {})

        merged_ai_tags = {**existing_ai_tags, "bg_removal": bg_removal_tags}

        update_payload: dict[str, Any] = {
            "processing_status": processing_status,
            "ai_tags": merged_ai_tags,
        }
        if image_clean_url is not None:
            update_payload["image_clean_url"] = image_clean_url
        if thumbnail_url is not None:
            update_payload["thumbnail_url"] = thumbnail_url

        await client.table("wardrobe_items").update(update_payload).eq("id", item_id).execute()

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        client = await _client_for(jwt)
        response = await client.table("users").select("plan_tier").limit(1).execute()
        if not response.data:
            return "free"
        first_row = cast(dict[str, Any], response.data[0])
        return str(first_row["plan_tier"])

    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        client = await _client_for(jwt)
        response = (
            await client.table("wardrobe_items").select("id").eq("id", item_id).limit(1).execute()
        )
        return bool(response.data)

    async def update_tagging_result(
        self,
        *,
        jwt: str,
        item_id: str,
        tag_columns: dict[str, Any] | None,
        tagging_tags: dict[str, Any],
    ) -> None:
        client = await _client_for(jwt)

        existing = (
            await client.table("wardrobe_items")
            .select("ai_tags")
            .eq("id", item_id)
            .limit(1)
            .execute()
        )
        existing_ai_tags: dict[str, Any] = {}
        if existing.data:
            existing_row = cast(dict[str, Any], existing.data[0])
            existing_ai_tags = dict(existing_row.get("ai_tags") or {})

        merged_ai_tags = {**existing_ai_tags, "tagging": tagging_tags}

        update_payload: dict[str, Any] = {"ai_tags": merged_ai_tags}
        if tag_columns is not None:
            update_payload.update(tag_columns)

        await client.table("wardrobe_items").update(update_payload).eq("id", item_id).execute()

    async def get_item_image_info(self, *, jwt: str, item_id: str) -> dict[str, Any] | None:
        client = await _client_for(jwt)
        response = (
            await client.table("wardrobe_items")
            .select("image_url, image_clean_url, thumbnail_url, processing_status")
            .eq("id", item_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return cast(dict[str, Any], response.data[0])

    async def get_items_image_info_bulk(
        self, *, jwt: str, item_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        client = await _client_for(jwt)
        response = (
            await client.table("wardrobe_items")
            .select("id, image_url, image_clean_url, thumbnail_url, processing_status")
            .in_("id", item_ids)
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        return {str(row["id"]): row for row in rows}

    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        client = await _client_for(jwt)
        response = await client.table("wardrobe_items").delete().eq("id", item_id).execute()
        return bool(response.data)

    async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        """(SS-020) Fetches ALL rows regardless of ``processing_status`` --
        see the port's own docstring for why (Open Question #7)."""
        client = await _client_for(jwt)
        response = (
            await client.table("wardrobe_items")
            .select(
                "id, category, color_primary, color_secondary, pattern, "
                "fabric, occasion_tags, season_tags, wear_count, last_worn_at, "
                "do_not_style, is_archived, condition, custom_tags"
            )
            .execute()
        )
        return cast(list[dict[str, Any]], response.data or [])

    async def get_items_for_rails(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        """(SS-048) Fetches ALL rows regardless of ``processing_status`` --
        same rationale as ``get_items_for_styling``. Separate select list
        (adds ``created_at``, drops the styling-only columns
        ``get_items_for_styling`` needs but the rails layer does not)."""
        client = await _client_for(jwt)
        response = (
            await client.table("wardrobe_items")
            .select("id, category, color_primary, created_at, wear_count, do_not_style, is_archived")
            .execute()
        )
        return cast(list[dict[str, Any]], response.data or [])

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        client = await _client_for(jwt)
        response = await client.table("users").select("style_preferences").limit(1).execute()
        if not response.data:
            return None
        first_row = cast(dict[str, Any], response.data[0])
        prefs = first_row.get("style_preferences")
        return cast(dict[str, Any] | None, prefs)

    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        """(SS-022) select city from users, RLS-scoped, mirrors
        get_plan_tier/get_style_preferences exactly -- never service_role."""
        client = await _client_for(jwt)
        response = await client.table("users").select("city").limit(1).execute()
        if not response.data:
            return None
        first_row = cast(dict[str, Any], response.data[0])
        city = first_row.get("city")
        return cast(str | None, city)
