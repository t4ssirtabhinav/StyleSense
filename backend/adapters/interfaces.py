"""Hexagonal port for wardrobe-item DB access (SS-011).

Placement note (per docs/tickets/SS-011-design.md's "Files to
create/modify"): CLAUDE.md's one-line description of ``adapters/`` names DB
access specifically ("WardrobeRepository / IWardrobeRepository"). R2 object
storage (see ``r2_storage.py`` in this same folder) doesn't fit that
description literally, but is the same *kind* of thing -- an adapter to an
external system, just cloud storage instead of Postgres -- so it lives here
too rather than inventing a new top-level folder.

Every concrete implementation must scope its Supabase client to the caller's
own JWT (never ``service_role``), so Postgres's own ``user_owns_wardrobe``
RLS policy (``auth.uid() = user_id``) is a real defense-in-depth backstop
against an application-layer bug passing the wrong ``user_id``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal


class IWardrobeRepository(ABC):
    """Never modify this signature to fit a new caller -- add a new method
    or a new adapter instead (Open/Closed, per CLAUDE.md)."""

    @abstractmethod
    async def upsert_uploaded_row(
        self,
        *,
        jwt: str,
        item_id: str,
        user_id: str,
        image_key: str,
    ) -> None:
        """Idempotent insert of the initial wardrobe_items row: id=item_id
        (the same UUID SS-010's get-upload-url Edge Function returned as
        itemId, overriding the column's DEFAULT gen_random_uuid()),
        category=NULL, processing_status='uploaded'. Must be a no-op (not an
        error) if the row already exists (ON CONFLICT (id) DO NOTHING) so a
        client retry of the same remove-bg call is safe."""
        raise NotImplementedError

    @abstractmethod
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
        """Merges ``bg_removal_tags`` under ai_tags.bg_removal without
        clobbering any other pre-existing top-level ai_tags keys (BL-053
        namespacing contract)."""
        raise NotImplementedError

    @abstractmethod
    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        """select plan_tier from users, scoped to the caller's own JWT (RLS
        user_owns_profile restricts this to one row, the caller's own)."""
        raise NotImplementedError
