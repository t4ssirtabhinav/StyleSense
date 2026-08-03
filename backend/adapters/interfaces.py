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
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


@dataclass(frozen=True)
class OccasionRegistrySnapshot:
    """(SS-025) An immutable point-in-time read of the ``occasions`` registry.

    ``keys`` is ordered by ``sort_order`` -- the Gemini prompt's occasion
    vocabulary is rendered from it in that order, so a newly-INSERTed
    occasion reaches the model with no code change and no redeploy.

    ``aliases`` maps ``occasion_aliases.alias -> occasion_key``.
    ``labels``/``badge_colors`` are carried for completeness (and for future
    prompt/rationale text); nothing in this ticket's backend paths needs
    them, and they must never become a second source of truth for the
    mobile app's rendering.

    Only ``is_active`` rows are ever fetched.
    """

    keys: tuple[str, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    badge_colors: dict[str, str] = field(default_factory=dict)


class IOccasionRepository(ABC):
    """Hexagonal port for reading the occasion registry (SS-025).

    Same contract as ``IWardrobeRepository`` below: every concrete
    implementation must scope its Supabase client to the CALLER'S OWN JWT
    (never ``service_role``). ``occasions``/``occasion_aliases`` are
    RLS-protected reference tables readable by ``authenticated``; using the
    caller's token keeps that policy in the loop instead of bypassing it for
    convenience.
    """

    @abstractmethod
    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        """Read active ``occasions`` (ordered by ``sort_order``) plus every
        ``occasion_aliases`` row. Raises on transport/RLS failure --
        ``OccasionNormalizer`` owns the fallback policy (last-known snapshot,
        else shape-only normalisation), so tagging never fails merely
        because the registry read did."""
        raise NotImplementedError


class IAppConfigRepository(ABC):
    """(SS-026) ALWAYS uses service_role -- see design §3.4 for why this port
    deliberately breaks the "never service_role" pattern every other
    adapters/ repository in this file follows. Raises on transport failure;
    AppConfigService owns the fallback/caching/typed-validation policy."""

    @abstractmethod
    async def fetch_all(self) -> dict[str, Any]:
        """Return {key: raw JSONB value} for every row. No filtering, no
        parsing -- AppConfigService validates per-key, lazily, on read()."""
        raise NotImplementedError


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
        ``occasion_tags``, ``season_tags``) on the UPDATE. (SS-025)
        ``occasion_tags`` is now ``TEXT[]`` of ``occasions`` registry slugs
        rather than ``occasion_type[]``; the caller normalises it before
        building ``tag_columns``, and the ``wardrobe_items``
        ``BEFORE INSERT OR UPDATE`` trigger normalises again as a backstop.
        Unknown slugs are written, never dropped. When ``None``
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

    @abstractmethod
    async def get_item_image_info(self, *, jwt: str, item_id: str) -> dict[str, Any] | None:
        """SELECT image_url, image_clean_url, thumbnail_url,
        processing_status ... .eq('id', item_id).limit(1), scoped to the
        caller's own JWT (SS-013; ``thumbnail_url`` added by SS-015 so this
        same method can double as the delete endpoint's "capture the R2
        keys before deleting the row" read, rather than adding a near-
        duplicate method).

        RLS's ``user_owns_wardrobe`` policy restricts visible rows to the
        caller's own -- a non-owned ``item_id`` returns 0 rows, identical to
        a nonexistent one, so this returns ``None`` for both. Callers (the
        new ``GET /wardrobe/items/{id}/image-url`` route) must map ``None``
        to a flat 404, never distinguishing "not yours" from "doesn't
        exist" (avoids turning this endpoint into an ownership oracle)."""
        raise NotImplementedError

    @abstractmethod
    async def get_items_image_info_bulk(
        self, *, jwt: str, item_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """SELECT id, image_url, image_clean_url, thumbnail_url,
        processing_status ... .in_('id', item_ids), scoped to the caller's
        own JWT (SS-014). RLS's ``user_owns_wardrobe`` policy already filters
        out ids the caller doesn't own -- those ids are simply absent from
        the returned dict, same "not an ownership oracle" posture as
        ``get_item_image_info`` above, not a per-id error. Keyed by ``id``
        (stringified) so the router can build ``BulkImageUrlsResponse.urls``
        directly from this dict."""
        raise NotImplementedError

    @abstractmethod
    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        """RLS-scoped ``.delete().eq('id', item_id)`` (SS-015). Returns
        whether a row was actually removed (``True``) vs. matched nothing
        (``False`` -- covers both "doesn't exist" and "not owned", same
        "not an ownership oracle" posture as ``get_item_image_info``).
        ``ON DELETE CASCADE`` on ``wardrobe_item_wears``' composite FK
        removes that item's wear-history rows as part of the same delete,
        no separate call needed."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SS-029 -- IRateLimiter / ICostLedger.
#
# Placed here, not in ai/ports/interfaces.py: CLAUDE.md scopes ai/ports/ to
# AI *provider capabilities* (IVisionProvider, IStylingProvider, ...); these
# two are infrastructure ports one layer below AI. adapters/interfaces.py
# already hosts non-AI external-system ports by documented precedent
# (IWardrobeRepository/Postgres, IOccasionRepository/Postgres,
# IAppConfigRepository/Postgres-service_role, R2 storage) -- see design
# doc §2.4. No new folder invented.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitDecision:
    """Amounts and ceilings are opaque non-negative integers -- micropaise
    for the cost budget gate, 1-per-call for a plain count limiter."""

    allowed: bool
    current: int | None  # post-INCRBY counter value; None when degraded
    ceiling: int
    degraded: bool  # True = decision came from the fail-open/closed fallback, not a real counter


class IRateLimiter(ABC):
    """Never widen this to fit a new backend -- add a new adapter instead
    (Open/Closed, per CLAUDE.md). The future Durable Objects adapter
    (``BL-082``) implements exactly this contract, which is the point of
    extracting it now."""

    @abstractmethod
    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        """Atomically add ``amount`` and decide from the returned total in
        ONE round-trip. MUST NOT read-then-write. On infra failure returns
        ``RateLimitDecision(allowed=fail_open, current=None, degraded=True)``."""
        raise NotImplementedError

    @abstractmethod
    async def adjust(self, *, key: str, delta: int) -> None:
        """Best-effort counter correction (refund or reconcile). Never
        raises; a failure is logged and never flips an already-made
        decision."""
        raise NotImplementedError


@dataclass(frozen=True)
class CostLedgerEntry:
    user_id: str
    request_id: str
    provider: str
    model: str
    feature: str
    cost_micropaise: int
    pricing_status: str  # 'priced' | 'estimated' | 'unpriced'
    unit_price_snapshot: dict[str, Any]
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    cache_hit: bool = False
    price_effective_from: str | None = None
    attempt: int = 1
    outcome: str = "success"  # 'success' | 'failed' | 'timeout' | 'denied'


class ICostLedger(ABC):
    @abstractmethod
    async def record(self, entry: CostLedgerEntry) -> None:
        """MUST NEVER RAISE. An accounting failure must never fail a user's
        request whose AI call already succeeded -- log and drop."""
        raise NotImplementedError

    @abstractmethod
    async def breakdown(
        self, *, user_id: str, since: date, until: date
    ) -> list[dict[str, Any]]:
        """Reads ``ai_cost_breakdown``. May raise -- this is an
        operator/BI read path, not on any user request path."""
        raise NotImplementedError
