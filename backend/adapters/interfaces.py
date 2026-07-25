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

    @abstractmethod
    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        """SELECT id ... .eq('id', item_id).limit(1), scoped to the
        caller's own JWT (SS-012). Backs ``POST /wardrobe/tag``'s
        synchronous existence check -- SS-012 only ever ``UPDATE``s, never
        ``INSERT``s (``BL-041`` directive), so the router must confirm the
        row already exists (created by ``POST /wardrobe/remove-bg``)
        *before* queuing any background task, returning 404 immediately
        rather than silently no-op'ing a 0-row UPDATE deep inside a
        background task (the ``BL-029`` precedent this guards against).

        Not named in the design doc's own "Files to create/modify" file
        list (which only calls out ``update_tagging_result`` by name), but
        required by that same doc's literal Endpoint-contract text ("a
        synchronous existence check... SELECT id on the RLS-scoped
        client") -- added as the minimal, hexagonal-consistent way to
        satisfy it without an inline Supabase call in the router (flagged
        explicitly in the worklog as a doc-internal gap-fill, not a
        divergence from anything the doc says explicitly)."""
        raise NotImplementedError

    @abstractmethod
    async def update_tagging_result(
        self,
        *,
        jwt: str,
        item_id: str,
        tag_columns: dict[str, Any] | None,
        tagging_tags: dict[str, Any],
    ) -> None:
        """Merges ``tagging_tags`` under ``ai_tags.tagging`` without
        clobbering any other pre-existing top-level ``ai_tags`` keys
        (``BL-053`` namespacing contract -- mirrors
        ``update_bg_removal_result``'s own ``ai_tags.bg_removal`` handling
        exactly, read-then-merge-then-write).

        ``tag_columns``, when not ``None``, is applied wholesale as the 8
        first-class columns (``category``, ``subcategory``,
        ``color_primary``, ``color_secondary``, ``pattern``, ``fabric``,
        ``occasion_tags``, ``season_tags``) on the UPDATE. When ``None``
        (a failed/timed-out tagging attempt), **no columns are written at
        all** -- only ``ai_tags.tagging`` is updated (to record
        ``status='failed'``), leaving any prior column values untouched.

        Known race (``BL-066``, amended A1): this app-level read-merge-
        write shares ``BL-036``'s concurrent-write class -- a tag-vs-tag or
        tag-vs-``bg_removal`` write racing this one can lose a key.
        Accepted-and-reduced (the in-flight marker collapses the common
        double-tap case) rather than fixed here; a durable fix would need
        an RPC/``jsonb_set``-in-``UPDATE``, deliberately deferred to
        preserve "no migration"."""
        raise NotImplementedError
