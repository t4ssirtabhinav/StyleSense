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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
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
    # (SS-020) Additive -- nothing shipped before this ticket could turn "an
    # occasion key" into the kind/formality/styling_rules triple
    # OccasionStylingInput requires. Backward-compatible (default_factory
    # dict, no existing caller reads them so none breaks). Keyed by
    # occasion key, populated from occasions.kind/formality/styling_rules
    # (columns that already exist -- SS-025 -- no schema change).
    kinds: dict[str, str] = field(default_factory=dict)
    formalities: dict[str, int] = field(default_factory=dict)
    styling_rules: dict[str, dict[str, Any]] = field(default_factory=dict)


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


@dataclass(frozen=True)
class SuggestionSessionLog:
    """(SS-033) One request's context. ``occasion`` is normalised again by
    008's ``trg_suggestion_sessions_normalize_occasion`` trigger -- the
    value read back may not be byte-identical to what was written (design
    §6.3/§3.1). ``cost_incurred``/``zero_cost_reason`` mirror the column
    default and its paired CHECK: alerting fails loud, never quiet."""

    user_id: str
    occasion: str | None = None
    weather_data: dict[str, Any] | None = None
    tier: str | None = None  # snapshot of users.plan_tier at request time
    effort_tier: str | None = None  # 'E0'..'E4'
    engine_version: str | None = None
    config_snapshot_hash: str | None = None
    candidate_count: int = 0
    cache_key: str | None = None
    request_id: str | None = None  # joins SS-029's ai_cost_ledger.request_id
    latency_ms: int | None = None
    cost_incurred: bool = True  # default matches the column default: fail loud
    zero_cost_reason: str | None = None  # REQUIRED when cost_incurred is False


@dataclass(frozen=True)
class SuggestionImpressionLog:
    """(SS-033) One scored candidate shown to a user, mapped 1:1 from a
    ``ScoredCandidate`` (design §5.3)."""

    rank: int  # 1-based; unique within a session
    item_ids: list[str]
    outfit_fingerprint: str  # 64-char lowercase hex, see design §5.3
    total_score: float  # [0.0, 1.0]
    rule_scores: list[dict[str, Any]] = field(default_factory=list)
    gap_flags: list[str] = field(default_factory=list)
    is_exploration: bool = False
    strategy: str | None = None


@dataclass(frozen=True)
class SuggestionOutcomeLog:
    """(SS-033) One user reaction to an impression. No ``user_id`` field --
    it is derived server-side from the impression's owner by the
    ``suggestion_outcome_set_user_id`` trigger, never supplied by the
    caller (design §3.5)."""

    impression_id: str
    outcome_type: str  # one of the five AC values
    outfit_id: str | None = None
    dedupe_key: str | None = None
    client_occurred_at: str | None = None  # ISO-8601; clamped by the adapter, see design §6.7
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImpressionRef:
    """(SS-023) One resolved ``suggestion_impressions`` row, the join target
    of ``POST /outfit-suggestions/outcome``'s ``(session_id, rank)`` pair.

    ``occasion`` is a doc-internal gap-fill (flagged explicitly, same
    posture as ``IWardrobeRepository.item_exists``'s own precedent): the
    design doc's dataclass sketch (§3) omits it, but design §7/test-plan
    item 7 requires ``OutfitOutcomeService`` to write ``outfits.occasion``
    from "the impression's own session row", and nothing else on this
    dataclass carries that value. Populated from a
    ``suggestion_impressions -> suggestion_sessions`` embedded read
    (``find_impression``'s own join), never from the request."""

    impression_id: str
    user_id: str  # from the impression row -- the ownership check's input
    session_id: str
    rank: int
    item_ids: list[str]
    outfit_fingerprint: str
    total_score: float
    is_exploration: bool
    occasion: str | None = None  # from suggestion_sessions.occasion, already normalised


@dataclass(frozen=True)
class OutfitInsert:
    """(SS-023) One row to write to ``outfits`` -- ``OutfitOutcomeService``'s
    payload to ``IOutfitRepository.insert_outfit``. Every value here is
    server-derived or engine-produced; nothing is a client-supplied
    free-form string except ``name`` (already length-capped by the
    router's Pydantic model)."""

    user_id: str
    item_ids: list[str]
    occasion: str | None  # from the impression's session row -- never client-asserted (design §7)
    name: str | None = None
    season: str | None = None
    ai_generated: bool = True
    ai_reasoning: str | None = None
    session_id: str | None = None
    outfit_fingerprint: str | None = None
    engine_version: str | None = None
    effort_tier: str | None = None
    reasoning_language: str | None = None
    items_snapshot: list[dict[str, Any]] = field(default_factory=list)


class IOutfitRepository(ABC):
    """(SS-023) JWT-scoped like ``IWardrobeRepository``, deliberately NOT
    ``service_role`` -- ``outfits`` keeps its ``user_owns_outfits`` FOR ALL
    policy (design §3's rejected-alternative note: this is the user's own
    authored content, not accounting data about them), so RLS remains the
    real enforcement and this port is not a privileged bypass."""

    @abstractmethod
    async def insert_outfit(self, *, jwt: str, outfit: OutfitInsert) -> tuple[str, bool]:
        """Insert one ``outfits`` row. Returns ``(outfit_id, already_existed)``.

        On a unique violation against ``uq_outfits_user_fingerprint``
        (``(user_id, outfit_fingerprint)`` -- a double swipe-right, a
        retried request, an offline replay), this method does NOT raise:
        it selects and returns the pre-existing row's id with
        ``already_existed=True``, mirroring
        ``suggestion_log_repository.py``'s ``_is_dedupe_conflict`` pattern.
        Any other failure raises -- unlike ``ISuggestionLogRepository``,
        this port's writes are user-facing (the ``outfits`` save IS the
        product action), so a genuine failure must reach the caller, not be
        swallowed."""
        raise NotImplementedError

    @abstractmethod
    async def insert_wear_rows(
        self,
        *,
        jwt: str,
        user_id: str,
        item_ids: list[str],
        worn_on: str,
        occasion_key: str | None,
        outfit_id: str,
    ) -> bool:
        """Insert one ``wardrobe_item_wears`` row per ``item_ids`` entry,
        ``outfit_id`` and ``occasion_key`` set on every row. Idempotent via
        ``ON CONFLICT DO NOTHING`` against
        ``wardrobe_item_wears_one_per_day_per_occasion`` (``015``,
        ``UNIQUE NULLS NOT DISTINCT (item_id, worn_on, occasion_key)``).
        Returns ``True`` if at least one row was newly inserted, ``False``
        if every item was already logged for that day/occasion (the
        "already logged for today" case, §6)."""
        raise NotImplementedError


class ISuggestionLogRepository(ABC):
    """(SS-033) ALWAYS uses service_role -- the second port in this file to
    do so after IAppConfigRepository, and for a different reason: these
    tables have NO write policy for any client role at all (design §3.5),
    because they are accounting-style data ABOUT a user rather than
    authored BY them, and the write can outlive the caller's JWT (it
    happens in a BackgroundTasks callback after the response was sent).

    NOTHING ON THIS PORT MAY RAISE. A logging failure must never fail the
    user's suggestion request (design §5.4). Failures are logged and
    swallowed; write methods return None and read methods return empty.

    Placement note (mirrors IAppConfigRepository/IOccasionRepository, per
    design §2.4): this is a Postgres persistence port, not an AI provider
    capability, so it lives in adapters/interfaces.py rather than
    ai/ports/interfaces.py.
    """

    @abstractmethod
    async def log_session(
        self,
        session: SuggestionSessionLog,
        impressions: Sequence[SuggestionImpressionLog],
    ) -> str | None:
        """Write ONE session row and ALL of its impression rows, then
        return the new session id (or None on any failure). Session and
        impressions are one call, not two, so a caller structurally cannot
        half-log a request. MUST NEVER RAISE."""
        raise NotImplementedError

    @abstractmethod
    async def log_outcome(self, outcome: SuggestionOutcomeLog) -> str | None:
        """Append one outcome row; returns its id, or None on failure or on
        a dedupe_key conflict (an already-recorded action -- not an error).
        MUST NEVER RAISE."""
        raise NotImplementedError

    @abstractmethod
    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Recent impressions for anti-repetition / novelty scoring, newest
        first. Returns [] on failure -- 'no history' degrades to 'no
        repetition penalty', never to a failed suggestion request. MUST
        NEVER RAISE."""
        raise NotImplementedError

    @abstractmethod
    async def update_session_outcome(
        self,
        *,
        session_id: str,
        cost_incurred: bool,
        request_id: str | None,
        latency_ms: int | None,
    ) -> None:
        """(SS-020) ``EngineV2._log_session`` always writes
        ``cost_incurred=False, zero_cost_reason='rules_only'`` (correct for
        Engine v2's own scope, since it never calls an AI provider) --
        SS-020's narration call, when it happens, is real spend that the
        same session row should reflect. Called once the narration outcome
        (cache hit / LLM call / degrade) is known, rather than reopening
        Engine v2's "no AI provider calls" boundary. MUST NEVER RAISE, same
        posture as every other method on this port."""
        raise NotImplementedError

    @abstractmethod
    async def find_impression(self, *, session_id: str, rank: int) -> ImpressionRef | None:
        """(SS-023) MUST NEVER RAISE (port-wide contract). Returns ``None``
        on not-found AND on any error -- the caller cannot distinguish, and
        must not try. Resolves on the ``(session_id, rank)`` UNIQUE
        constraint (``suggestion_impressions_session_rank_unique``,
        ``013:126``).

        ``service_role``, so this BYPASSES RLS ENTIRELY and will happily
        return any user's impression -- ``OutfitOutcomeService`` MUST
        compare ``ImpressionRef.user_id`` against the JWT-derived caller
        before any write (design §3, the single highest-risk line in the
        ticket)."""
        raise NotImplementedError


@dataclass(frozen=True)
class WearRecency:
    """(SS-035) One item's occasion-scoped wear recency, mapped 1:1 from a
    ``public.wear_recency()`` row. ``last_worn_on_for_occasion`` is ``None``
    when the item has never been worn for the queried occasion -- SQL's own
    three-valued logic (``occasion_key = p_occasion_key`` is never true when
    either side is ``NULL``) makes a backfilled/unknown-occasion row
    structurally incapable of matching, so this is never a false positive."""

    item_id: str
    last_worn_on: date | None
    last_worn_on_for_occasion: date | None  # None means "never worn for this occasion"
    wears_for_occasion: int


class IWearHistoryRepository(ABC):
    """(SS-035) Read-only occasion-scoped wear recency for novelty scoring.

    RLS-scoped via the caller's JWT (the SupabaseOccasionRepository /
    SupabaseWardrobeRepository shape), NOT service_role: this is the user's
    own wardrobe data, read on their behalf, inside their own request.

    MUST NEVER RAISE. 'No history' degrades to 'no novelty penalty', never
    to a failed suggestion request -- the same posture as
    ISuggestionLogRepository.recent_impressions.

    Placement note (mirrors IAppConfigRepository/IOccasionRepository/
    ISuggestionLogRepository, per design §2.4): this is a Postgres
    persistence port, not an AI provider capability, so it lives in
    adapters/interfaces.py rather than ai/ports/interfaces.py. A new port
    rather than three more methods on IWardrobeRepository because the
    consumer is the styling engine (not the upload/tagging pipeline
    IWardrobeRepository serves), it is read-only where that port is
    write-heavy, and SS-033 set the precedent of one port per new
    read/log surface.

    Nothing in this repo calls fetch_wear_recency yet -- Engine v2 / SS-020
    owns the wiring (BL-119).
    """

    @abstractmethod
    async def fetch_wear_recency(
        self, *, jwt: str, user_id: str, occasion_key: str | None = None
    ) -> list[WearRecency]:
        """One row per item the user has ever worn, newest-first is NOT
        guaranteed (the caller indexes by item_id). Returns [] on any
        failure. MUST NEVER RAISE."""
        raise NotImplementedError


@dataclass(frozen=True)
class GarmentTypeRow:
    """(SS-034/SS-038) One raw ``garment_types`` row, as fetched -- the
    adapter layer's shape, not the pure-scoring layer's. ``GarmentRegistryAdapter``
    (``services/garment_registry_adapter.py``) maps this onto
    ``engine_v2_types.GarmentAttributes`` (which folds in the 6-value
    ``assembly_slot`` and pulls ``volume_class`` out of ``styling_rules``)."""

    key: str
    slot: str
    layer: int
    register: tuple[str, ...]
    base_formality: int
    pairs_with: tuple[str, ...]
    requires_with: tuple[str, ...]
    excludes_with: tuple[str, ...]
    styling_rules: dict[str, Any]


@dataclass(frozen=True)
class GarmentRegistrySnapshot:
    """(SS-034/SS-038) An immutable point-in-time read of the
    ``garment_types``/``garment_type_aliases`` registry. ``rows`` is keyed by
    ``garment_types.key``; ``aliases`` maps ``garment_type_aliases.alias ->
    garment_key``. Only ``is_active`` rows are ever fetched."""

    rows: dict[str, GarmentTypeRow] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)


class IGarmentRegistryRepository(ABC):
    """(SS-038) ALWAYS uses ``service_role`` -- see
    ``adapters/garment_registry_repository.py``'s module docstring for why
    this deliberately breaks the "never service_role" pattern most other
    repositories in this file follow (mirrors ``IAppConfigRepository``'s
    precedent): ``garment_types`` is non-user-owned reference data, its RLS
    policy requires only ``auth.role() = 'authenticated'`` (no per-user
    ownership), and ``GarmentRegistryAdapter.get_garment_attributes`` must be
    callable with no ``jwt`` in hand, inside the hot scoring loop.

    Raises on transport failure -- ``GarmentRegistryAdapter`` owns the
    stale-or-empty-serving fallback policy (mirrors
    ``OccasionNormalizer.get_registry``)."""

    @abstractmethod
    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        """Read every active ``garment_types`` row plus every
        ``garment_type_aliases`` row. No ``jwt`` parameter -- see class
        docstring."""
        raise NotImplementedError


@dataclass(frozen=True)
class FabricAttributes:
    """(SS-036/SS-038) One ``fabrics`` row's Engine v2-relevant attributes.
    ``season_affinity is None`` means "no seasonal opinion" (true today for
    ``silk``/``khadi``, ``BL-125``'s flagged rows) -- never treat that as
    "matches no season", see ``engine_v2_attribute_scoring.fabric_weather_score``.

    Defined here (not ``engine_v2_types.py``) so ``IFabricRegistryRepository``
    below can reference it without ``adapters/`` importing from ``services/``
    -- this repo's established import direction is ``services -> adapters``,
    never the reverse. ``engine_v2_types.py`` re-exports this name so callers
    in ``services/`` never need to know it physically lives here."""

    key: str
    weight: str | None
    breathability: int | None
    season_affinity: tuple[str, ...] | None


class IFabricRegistryRepository(ABC):
    """(SS-038) ALWAYS uses ``service_role`` -- same justification as
    ``IGarmentRegistryRepository`` above (non-user-owned reference data,
    ``authenticated_read_fabrics`` RLS policy has no per-user ownership).

    Raises on transport failure -- callers (``engine_v2.py``) degrade this to
    an empty dict on failure, since a per-request plain fetch (not
    TTL-cached, unlike the garment registry -- see
    ``adapters/fabric_registry_repository.py``'s module docstring) is cheap
    enough to just retry next request."""

    @abstractmethod
    async def fetch_all(self) -> dict[str, FabricAttributes]:
        """Return {key: FabricAttributes} for every active ``fabrics`` row."""
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

    @abstractmethod
    async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        """(SS-020) RLS-scoped via the caller's own JWT (mirrors every
        other method on this port). Selects ``id, category, color_primary,
        color_secondary, pattern, fabric, occasion_tags, season_tags,
        wear_count, last_worn_at, do_not_style, is_archived, condition,
        custom_tags`` (the last four added by SS-040) for the caller's own
        rows -- fetches ALL rows regardless of ``processing_status`` (Open
        Question #7): Engine v2's own eligibility stage already excludes
        items missing ``category``/``color_primary``, counting them in the
        gap report, so including untagged items is safe (excluded
        downstream, not silently dropped) and the gap-report count becomes a
        useful "how much of your wardrobe isn't tagged yet" signal.
        ``do_not_style``/``is_archived`` are read by
        ``engine_v2_eligibility.filter_eligible`` to exclude items from the
        eligible pool (SS-040) -- this select list is the single point of
        failure for that feature: omitting a column here silently makes it
        a no-op regardless of what the pydantic model declares."""
        raise NotImplementedError

    @abstractmethod
    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        """(SS-020) Selects ``users.style_preferences``, RLS-scoped, mirrors
        ``get_plan_tier``'s existing shape. Returns ``None`` when the row/
        column is absent -- caller degrades to empty preferences, never
        raises."""
        raise NotImplementedError

    @abstractmethod
    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        """(SS-022) Selects ``users.city``, RLS-scoped, mirrors
        ``get_plan_tier``/``get_style_preferences``'s existing shape.
        Returns the raw stored value verbatim -- may be ``None``, ``''``,
        one of the 50 ``TOP_50_INDIAN_CITIES`` display names, or arbitrary
        free text from the picker's "Other" row (design §2). Resolution
        against the coordinate table is ``services/india_city_coordinates
        .resolve_city``'s job, not this port's."""
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

    @abstractmethod
    async def peek(self, *, key: str) -> int | None:
        """(SS-039) Advisory-only, NON-mutating read of a counter's current
        value (``None`` on a missing key or any infra failure -- never
        raises). NEVER used for an allow/deny decision:
        ``check_and_consume``'s atomic ``INCRBY`` remains the ONLY
        enforcement path in this codebase. This method exists solely so a
        caller can ask "roughly how close is this user to their ceiling
        right now" (``CostBudgetGate.budget_status()``) without perturbing
        the ceiling itself."""
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
    async def breakdown(self, *, user_id: str, since: date, until: date) -> list[dict[str, Any]]:
        """Reads ``ai_cost_breakdown``. May raise -- this is an
        operator/BI read path, not on any user request path."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SS-020 -- ISuggestionNarrationCacheRepository.
#
# The combination-signature cache (design §3/§4): a NARRATION-ONLY cache --
# Engine v2's own per-user personalisation is never cached, only the LLM's
# prose for a coarsened, salted, cross-user-shareable candidate-attribute
# signature. No user_id/item-id column at all, by construction (the
# structural half of "not reversible into another user's wardrobe" -- the
# other half is compute_narration_signature never hashing raw item
# attributes or ids).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedNarration:
    """One cache hit's payload. ``narrations_by_signature_index`` maps the
    candidate's position in the (sorted, order-independent) signature array
    to its cached rationale string -- never item ids, never user_id."""

    narrations_by_signature_index: dict[int, str]
    language: str


class ISuggestionNarrationCacheRepository(ABC):
    """ALWAYS uses ``service_role`` (mirrors ``IAppConfigRepository``/
    ``ISuggestionLogRepository`` precedent) -- this table has no per-user
    ownership at all, by design (that's the point, not a shortcut: see
    ``suggestion_narration_cache_repository.py``'s module docstring).

    Both methods MUST NEVER RAISE -- a cache failure degrades to "always
    call the LLM," never to a failed request."""

    @abstractmethod
    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        """Returns ``None`` on a cache miss OR any failure -- the caller
        cannot distinguish the two, by design (both degrade identically:
        call the LLM). MUST NEVER RAISE."""
        raise NotImplementedError

    @abstractmethod
    async def put(
        self,
        *,
        signature_hash: str,
        occasion_key: str,
        engine_version: str,
        narrations_by_signature_index: dict[int, str],
        language: str,
        ttl_seconds: int,
    ) -> None:
        """Best-effort write -- never blocks the caller's response on a
        cache-write failure. MUST NEVER RAISE."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SS-022 -- IWeatherProvider.
#
# Placed here (not ai/ports/interfaces.py): this is infrastructure one layer
# below an AI *provider capability* (that file's own scoping comment) --
# same precedent as IRateLimiter/ICostLedger/IFabricRegistryRepository
# above. Open-Meteo needs no auth/key, so unlike every AI port in this repo
# this one carries no user identity at all -- only a city's public lat/lng.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeatherObservation:
    """One provider's raw current-weather reading. Never surfaced to a
    caller directly -- ``services/weather_rules.WeatherContext`` is the
    derived, in-app shape everything downstream actually consumes."""

    temp_c: float
    humidity: int  # relative humidity %
    weather_code: int  # WMO code, raw
    precipitation_mm: float
    observed_at: str  # ISO-8601 as returned by the provider


class IWeatherProvider(ABC):
    """Never modify this signature to fit a new provider -- add a new
    adapter class instead (Open/Closed, per CLAUDE.md)."""

    @abstractmethod
    async def fetch_current(self, *, lat: float, lng: float) -> WeatherObservation | None:
        """MUST NEVER RAISE -- every timeout/HTTP/parse failure returns
        ``None``. Same never-raise contract as ``ISuggestionLogRepository``
        and ``ISuggestionNarrationCacheRepository`` (SS-020)."""
        raise NotImplementedError
