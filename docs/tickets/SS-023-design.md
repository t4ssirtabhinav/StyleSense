# SS-023 — Outfit Suggestion UI (Occasion Flow) — Design

## Scope restatement

Turn the Style tab from an `EmptyState` placeholder into the product's primary AI surface: a dynamic occasion grid (sourced from the SS-025 `occasions` registry, not a hardcoded list), a "Get suggestions" CTA that reaches results in ≤2 taps, an animated skeleton deck while `POST /outfit-suggestions/portfolio` (SS-020, shipped in PR #41) runs synchronously, and a Tinder-style swipe deck of outfit cards — each showing stacked item thumbnails, an occasion badge, a score badge and an expandable AI reasoning snippet. Swipe right persists the outfit; swipe left dismisses it; "Not quite right — regenerate" fetches a genuinely different set; an accepted outfit offers a share action.

Two premises in the briefing and the raw ticket's Technical Notes are **factually wrong against the current repo, and this design corrects them rather than building on them**:

1. **`outfits` is not a new table and this ticket does not create it.** It has existed since `001_initial.sql:80-94`, with RLS enabled and a `user_owns_outfits` FOR ALL policy (`001_initial.sql:168`), its `occasion` column already converted to `TEXT` with a normalisation trigger (`008_occasion_columns_to_text.sql:20,79-81`), and it is already referenced by three FKs (`suggestion_sessions.accepted_outfit_id`, `social_posts.outfit_id`, `suggestion_outcomes.outfit_id`, `wardrobe_item_wears.outfit_id`). SS-023 is the **first writer**, not the creator. The migration this ticket ships is therefore an *additive hardening* migration (`020`), not a `CREATE TABLE`. SS-015's design doc already said this correctly ("`outfits`/`suggestion_sessions` exist in `001_initial.sql` but no code anywhere writes to them yet") — the raw ticket's "this is the ticket that creates the `outfits` table" line is the stale one.
2. **Accept/reject cannot be a client-only Supabase write.** The canonical record of a user's reaction to a suggestion is SS-033's `suggestion_outcomes` (`013_suggestion_impressions.sql:148-159`, `outcome_type IN ('saved','worn','dismissed','shuffled_away','shared')` with an `outfit_id` FK), and that table — like `suggestion_impressions` and `suggestion_sessions` — deliberately has **no INSERT policy for any client role** (`013:192-197`: "ABSENCE OF A POLICY *IS* THE WRITE-PROTECTION MECHANISM"). So the swipe must go through a new backend endpoint. That, plus the fact that SS-020's shipped response carries **no `session_id`, no `rank`, no `outfit_fingerprint`** (nothing the client could use to identify which impression it is reacting to), and no cache-bypass/exclusion parameter for the regenerate AC, means this ticket carries a real backend leg. It is designed here rather than split out, because every one of the ticket's five acceptance criteria except "reasoning is expandable" is unsatisfiable without it (see Open Question #1 on the resulting estimate).

## Files to create/modify

### Mobile — new (`mobile/features/outfit-ai/`, a new domain folder per CLAUDE.md's `features/<domain>/` convention)

- `mobile/features/outfit-ai/outfit-ai.types.ts` — request/response types mirroring the backend Pydantic models verbatim (see "Concrete values" §1). No `any`; nothing inline in components.
- `mobile/features/outfit-ai/outfit-ai.service.ts` — raw `fetch` calls to `${EXPO_PUBLIC_BACKEND_URL}/outfit-suggestions/portfolio` and `/outfit-suggestions/outcome`, `Authorization: Bearer ${jwt}`, exactly the shape `wardrobe.service.ts`'s `postWardrobeAction`/`fetchWardrobeItemImageUrl` already established (`constants/api.ts` for the base URL, never a literal host).
- `mobile/features/outfit-ai/outfit-ai.queries.ts` — React Query hooks. **The only place the service layer is called from.** `useGenerateSuggestionsMutation`, `useRecordOutcomeMutation`, `useWardrobeItemCountQuery` (re-exported/reused from `wardrobe.queries.ts` if one already exists — check `fetchWardrobeItemCount` in `wardrobe.service.ts` before adding a second).
- `mobile/features/outfit-ai/outfit-ai.store.ts` — Zustand: `selectedOccasionKey`, `deckIndex`, `dismissedFingerprints: string[]` (the regenerate exclusion set, session-scoped, cleared on occasion change), `sessionId`. Typed selectors only.
- `mobile/features/outfit-ai/components/OccasionGrid.tsx` — icon grid over `useOccasionTaxonomy().topLevelOccasions`.
- `mobile/features/outfit-ai/components/SuggestionSkeletonDeck.tsx` — 3 stacked `Skeleton` cards, the loading state.
- `mobile/features/outfit-ai/components/OutfitCardDeck.tsx` — swipe/gesture container, deck state machine, accept/reject callbacks.
- `mobile/features/outfit-ai/components/OutfitCard.tsx` — one card: item stack, occasion badge, score badge, reasoning disclosure, action buttons.
- `mobile/features/outfit-ai/components/OutfitItemStack.tsx` — stacked `expo-image` thumbnails driven by the existing bulk image-URL hook (`useWardrobeItemImageUrls`, SS-014).
- `mobile/features/outfit-ai/components/ReasoningDisclosure.tsx` — collapsed 2-line snippet → expanded full rationale (AC #3).
- `mobile/features/outfit-ai/components/AcceptedOutfitPanel.tsx` — post-accept confirmation with the Share action (AC #4) and the optional "Wore this today" action (BL-120, see §6).
- `mobile/features/outfit-ai/share/outfitCardExport.ts` — the **capability seam** for PNG export: `exportOutfitCard(ref) => Promise<ShareableCard>` where `ShareableCard = { kind: 'image'; uri: string } | { kind: 'text'; body: string }`. Platform files (`.native.ts` / `.web.ts`) resolve the concrete implementation. **The concrete image implementation is blocked on Open Question #2** — the text fallback is what ships if that question resolves to "defer".
- `mobile/features/outfit-ai/outfit-ai.constants.ts` — copy strings, deck size, exclusion cap.

### Mobile — modify

- `mobile/app/(tabs)/style.tsx` — replace the `EmptyState` placeholder with the real screen. **Keep** the existing `?occasion=` deep-link handling and its `resolveOccasion` alias pass (`style.tsx:22-33`) — it is load-bearing for legacy SS-005 deep links and must survive verbatim in behaviour, now pre-selecting a grid tile instead of changing a heading.
- `mobile/types/supabase.ts` — regenerate after migration `020` (the `outfits` row type gains columns). Auto-generated only, never hand-edited.
- No change to `mobile/constants/analyticsEvents.ts` — `FIRST_SUGGESTION_VIEWED`, `FIRST_OUTFIT_SAVED` and `OUTFIT_SHARED` already exist (`analyticsEvents.ts:22-27`) with the right property shapes; this ticket supplies their first real call sites (closes the SS-023 portion of `BL-049` and all of `BL-034`).
- **No new `components/ui/` primitive.** Checked SS-008's kit (`components/ui/index.ts`): `Card`, `Badge`, `Button`, `IconButton`, `Text`, `Skeleton`, `EmptyState`, `ProgressBar`, `Avatar`, `AppBottomSheet` cover every visual element of the card. The swipe *interaction* is domain behaviour (a suggestion deck), not a reusable design-system primitive, so it lives in `features/outfit-ai/components/`, per the raw ticket's own "only if genuinely needed" instruction.

### Backend — modify

- `backend/routers/outfit_suggestions.py` — (a) additive fields on `GeneratePortfolioRequest`/`PortfolioItemResponse`/`GeneratePortfolioResponse` (§1); (b) new `POST /outfit-suggestions/outcome` behind the same real `Depends(get_current_user_id)`. The `/generate` stub route and `get_current_user_id_stub` stay byte-identical and untouched (`BL-052`'s scope note, reaffirmed).
- `backend/services/outfit_portfolio_service.py` — thread `exclude_fingerprints` into the engine call; surface `session_id`, per-candidate `rank` and `outfit_fingerprint` in the returned dict.
- `backend/services/engine_v2.py` — additive optional kwarg `exclude_fingerprints: frozenset[str] | None = None`, forwarded to portfolio selection. Default `None` = today's behaviour exactly, so every shipped SS-038 test keeps passing unmodified (same additive-widening pattern SS-020 already used on this file).
- `backend/services/engine_v2_portfolio.py` — apply the exclusion filter after scoring and **before** MMR selection, using the existing `compute_outfit_fingerprint` (`engine_v2_portfolio.py`'s own, not `suggestion_log_service.py`'s colon-joined variant — `BL-134`'s two implementations stay unconsolidated; this ticket must use the one `suggestion_impressions.outfit_fingerprint` is actually written with, i.e. the SS-038 one via `EngineV2._log_session`).
- `backend/adapters/interfaces.py` — add `IOutfitRepository` (JWT-scoped, see §3) and one never-raise method on `ISuggestionLogRepository`: `find_impression(*, session_id: str, rank: int) -> ImpressionRef | None`.
- `backend/adapters/suggestion_log_repository.py` — implement `find_impression` (service_role, wrapped in try/except, returns `None` on any failure).

### Backend — new

- `backend/services/outfit_outcome_service.py` — orchestrates one swipe: resolve impression → **verify caller ownership** → (on accept) insert `outfits` → insert `suggestion_outcomes` → (optional, §6) insert `wardrobe_item_wears`.
- `backend/adapters/outfit_repository.py` — `SupabaseOutfitRepository(IOutfitRepository)`, **JWT-scoped `.postgrest.auth(jwt)` like `wardrobe_repository.py`, not `service_role`** (see §3 for why this is the deliberate choice).

### Migration

- `supabase/migrations/020_outfits_first_writer.sql` — additive hardening of the existing `outfits` table (§2). `019` is taken by SS-020 and is already live on the linked project (see `docs/worklog/SS-020.md`'s "CI fix" entry). Per `BL-110`'s standing discipline, re-confirm `020` is still free via `supabase migration list --linked` immediately before push — worktrees for SS-020/SS-021/SS-035/SS-038/SS-039 exist in parallel and any of them could claim it first.

### Tests

`backend/tests/test_outfit_outcome_service.py`, `test_outfit_suggestions_router_outcome.py`, `test_outfit_portfolio_service.py` (extend), `test_engine_v2_exclusion.py`, `test_db_schema.py` (extend); `mobile/__tests__/app/(tabs)/style.test.tsx` (rewrite), plus one file per new component/hook under `mobile/__tests__/features/outfit-ai/`. Detail in "Test plan".

## Concrete values to use, not invent

### 1. API contracts

**`POST /outfit-suggestions/portfolio` — additive changes only.** Every existing field keeps its name, type and meaning (SS-020 shipped and merged; nothing here is a rename or a removal).

```python
class GeneratePortfolioRequest(BaseModel):
    occasion: str
    season: Literal["summer", "winter", "monsoon", "all"] | None = None
    as_of: date | None = None
    style_preferences_override: dict[str, Any] | None = None
    # NEW (SS-023) -- the regenerate mechanism. Fingerprints the caller has
    # already been shown/dismissed in this session. Untrusted but harmless:
    # the only thing a forged value can do is shrink the caller's own result
    # set. Capped server-side; over-cap is TRUNCATED (oldest-first by client
    # order), never a 422.
    exclude_fingerprints: list[str] = Field(default_factory=list, max_length=60)


class PortfolioItemResponse(BaseModel):
    item_ids: list[str]
    category_labels: dict[str, str]
    total_score: float
    rationale: str
    rationale_language: Literal["en", "hi"]
    is_exploration: bool
    gap_flags: list[str]
    # NEW (SS-023)
    rank: int                      # 1-based, EXACTLY the rank written to
                                   # suggestion_impressions.rank by
                                   # EngineV2._log_session -- this is the
                                   # join key the outcome endpoint resolves on
    outfit_fingerprint: str        # 64-char lowercase hex, from
                                   # engine_v2_portfolio.compute_outfit_fingerprint


class GeneratePortfolioResponse(BaseModel):
    portfolio: list[PortfolioItemResponse]
    limited_options: bool
    gap_report: dict[str, Any]
    engine_version: str
    effort_tier: str
    cache_hit: bool
    generated_at: str
    # NEW (SS-023)
    session_id: str | None         # None when session logging failed -- the
    occasion_key: str              # RESOLVED canonical key (post-alias), so
                                   # the client badges/persists the same
                                   # identity the DB and engine use
```

`session_id` is `str | None` on purpose: `EngineV2._log_session` is best-effort and already returns `None` on a logging failure (`engine_v2.py:290-293`, `suggestion_log_repository.py:152-175`). A `None` session must still render suggestions — it only means outcomes cannot be recorded for that batch (see Edge cases).

**`POST /outfit-suggestions/outcome` — new.**

```python
class RecordOutcomeRequest(BaseModel):
    session_id: str                 # UUID string, from the portfolio response
    rank: int = Field(ge=1)         # which card in that session
    outcome_type: Literal["saved", "dismissed", "worn", "shared"]
    client_occurred_at: str | None = None   # ISO-8601; clamped server-side by
                                            # the existing _clamp_client_occurred_at
    name: str | None = Field(default=None, max_length=80)  # optional user-given outfit name


class RecordOutcomeResponse(BaseModel):
    outfit_id: str | None           # non-None for 'saved'/'worn'; None for 'dismissed'
    outcome_recorded: bool          # False = outcome logging degraded (see below)
    already_saved: bool             # True when the idempotent path hit an existing outfit
```

Status codes: `200` on success, `401` on missing/invalid JWT (real `get_current_user_id`), `404` when the `(session_id, rank)` pair does not resolve to an impression **or resolves to one owned by a different user** (deliberately the same 404 for both — a 403 would confirm the session exists, an enumeration oracle over another user's session ids). Never a 500 for a degraded log write.

`'shuffled_away'` is in the DB's CHECK enum but is **not** exposed by this request model — this ticket has no shuffle gesture. Adding it later is an additive `Literal` widening, no migration.

### 2. Migration `020_outfits_first_writer.sql` — additive hardening of an existing, empty table

```sql
-- SS-023 -- first writer to `outfits` (created in 001_initial.sql, never
-- written by any code path to date). Forward-only; 001 is NEVER edited
-- (BL-060). Every statement below is additive or a tightening that is safe
-- ONLY because the table is empty -- Developer MUST confirm
-- `SELECT count(*) FROM outfits` is 0 on the linked project before push and
-- record the result in the worklog.

ALTER TABLE outfits
  ADD COLUMN session_id         UUID REFERENCES suggestion_sessions(id) ON DELETE SET NULL,
  ADD COLUMN outfit_fingerprint TEXT,
  ADD COLUMN engine_version     TEXT,
  ADD COLUMN effort_tier        TEXT,
  ADD COLUMN reasoning_language TEXT,
  ADD COLUMN items_snapshot     JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE outfits
  ALTER COLUMN user_id SET NOT NULL,                       -- safe: table empty; a NULL
                                                           -- user_id row is invisible to
                                                           -- the RLS predicate anyway
  ADD CONSTRAINT outfits_item_ids_nonempty_check
    CHECK (item_ids IS NULL OR array_length(item_ids, 1) >= 1),
  ADD CONSTRAINT outfits_fingerprint_shape_check
    CHECK (outfit_fingerprint IS NULL OR outfit_fingerprint ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT outfits_effort_tier_check
    CHECK (effort_tier IS NULL OR effort_tier IN ('E0','E1','E2','E3','E4')),
  ADD CONSTRAINT outfits_reasoning_language_check
    CHECK (reasoning_language IS NULL OR reasoning_language IN ('en','hi')),
  ADD CONSTRAINT outfits_user_rating_range_check
    CHECK (user_rating IS NULL OR user_rating BETWEEN 1 AND 5);

-- Idempotent save: a double swipe-right (double tap, retried request, offline
-- replay) collapses onto one row instead of creating a duplicate outfit.
-- Partial, so hand-curated outfits (SS-024+) with no fingerprint are unaffected.
CREATE UNIQUE INDEX uq_outfits_user_fingerprint
  ON outfits (user_id, outfit_fingerprint) WHERE outfit_fingerprint IS NOT NULL;

CREATE INDEX idx_outfits_user_created ON outfits (user_id, created_at DESC);
CREATE INDEX idx_outfits_session      ON outfits (session_id);
CREATE INDEX idx_outfits_item_ids     ON outfits USING GIN (item_ids);

COMMENT ON COLUMN outfits.items_snapshot IS
  'Denormalised {item_id, category, color_primary, image_path} per item AT SAVE TIME. '
  'Deliberate redundancy: item_ids is a plain UUID[] with NO foreign key (same posture as '
  'suggestion_impressions.item_ids, 013_suggestion_impressions.sql:129-132), so deleting a '
  'wardrobe item cannot erase or corrupt a saved outfit. This snapshot is what lets a saved '
  'outfit still RENDER after one of its items is deleted -- resolving the edge case SS-014 and '
  'SS-015 both deferred as forward-looking (docs/tickets/SS-015-design.md:208).';
COMMENT ON COLUMN outfits.session_id IS
  'Provenance: which suggestion_sessions row produced this outfit. Nullable and ON DELETE SET '
  'NULL because SS-033s 180-day retention purge (public.purge_suggestion_logs) will delete the '
  'session long before the user deletes the outfit -- an outfit must survive its own provenance.';
COMMENT ON COLUMN outfits.suggestions IS NULL;  -- (no-op placeholder; do not add)

-- RLS: DELIBERATELY UNCHANGED. `user_owns_outfits` (001_initial.sql:168) stays
-- FOR ALL. See design 3 for why this ticket does NOT repeat 013's
-- write-policy removal here.

-- ============================================================
-- ROLLBACK (safe only while outfits is still empty):
--   DROP INDEX IF EXISTS idx_outfits_item_ids;
--   DROP INDEX IF EXISTS idx_outfits_session;
--   DROP INDEX IF EXISTS idx_outfits_user_created;
--   DROP INDEX IF EXISTS uq_outfits_user_fingerprint;
--   ALTER TABLE outfits
--     DROP CONSTRAINT IF EXISTS outfits_user_rating_range_check,
--     DROP CONSTRAINT IF EXISTS outfits_reasoning_language_check,
--     DROP CONSTRAINT IF EXISTS outfits_effort_tier_check,
--     DROP CONSTRAINT IF EXISTS outfits_fingerprint_shape_check,
--     DROP CONSTRAINT IF EXISTS outfits_item_ids_nonempty_check,
--     ALTER COLUMN user_id DROP NOT NULL,
--     DROP COLUMN IF EXISTS items_snapshot,
--     DROP COLUMN IF EXISTS reasoning_language,
--     DROP COLUMN IF EXISTS effort_tier,
--     DROP COLUMN IF EXISTS engine_version,
--     DROP COLUMN IF EXISTS outfit_fingerprint,
--     DROP COLUMN IF EXISTS session_id;
-- ============================================================
```

Reused verbatim, not re-invented: `name`, `item_ids`, `occasion`, `season`, `ai_generated`, `ai_reasoning`, `user_rating`, `worn_count`, `last_worn_at`, `avatar_image_url`, `created_at` all already exist on the table and keep their `001` meanings. `trg_outfits_normalize_occasion` (`008:79-81`) already fires `BEFORE INSERT OR UPDATE` — **no new trigger**, and callers must not assert round-trip equality on `occasion` (an alias normalises to its canonical key), exactly as `013:80-85` warns for `suggestion_sessions`.

### 3. The write path and its auth boundary (the load-bearing security decision)

One swipe = up to three writes across three tables with three different access postures:

| Table | Policy today | Who writes it here | Why |
|---|---|---|---|
| `outfits` | `user_owns_outfits` FOR ALL (`001:168`) | backend, **JWT-scoped client** (`.postgrest.auth(jwt)`) | It is the user's own private content. CLAUDE.md: "All user data queries MUST use authenticated Supabase client." RLS remains the enforcement, the backend is not a privileged bypass. |
| `suggestion_outcomes` | no write policy for any client role (`013:192-197`) | backend, **`service_role`** via the existing `SupabaseSuggestionLogRepository.log_outcome` | Already built, already service_role, already never-raises. Nothing new. |
| `wardrobe_item_wears` | `user_owns_item_wears` FOR ALL WITH CHECK (`006:38-41`) | backend, **JWT-scoped** (only if §6 is in scope) | Same reasoning as `outfits`. |

**Rejected alternative, recorded so it isn't re-litigated:** mirroring `013`'s `DROP POLICY "user_owns_sessions"` move and stripping `outfits` down to read-own + service_role writes. Rejected because (a) `outfits` is authored *by* the user, not accounting data *about* them — the exact distinction `suggestion_log_repository.py`'s module docstring uses to justify its own service_role exception; (b) it is a policy change on a shipped table with three dependent FKs, i.e. a one-way door bought for no security gain (the only thing a client could forge is a row in its own private outfit list, with no cost, money or cross-user surface); (c) SS-024/social will plausibly need client-side outfit edits. Keeping FOR ALL is the smaller, reversible choice.

**The one genuinely new auth check, and the thing QA must attack hardest:** `SupabaseSuggestionLogRepository` is `service_role`, which *bypasses RLS entirely*. So `find_impression(session_id, rank)` will happily return **any** user's impression. `OutfitOutcomeService` MUST compare the returned `user_id` against the JWT-derived `user_id` and 404 on mismatch, before any write. Without that comparison, `POST /outfit-suggestions/outcome` is a cross-tenant write primitive (attacker supplies a guessed session UUID; the outfit lands in the attacker's own `outfits`, but `suggestion_outcomes` — the personalisation and quality-measurement corpus — gets poisoned under the victim's `user_id`, since `trg_suggestion_outcomes_set_user_id` derives `user_id` from the *impression*, not from the caller). This is the single highest-risk line in the ticket.

```python
# backend/adapters/interfaces.py  (additive)
@dataclass(frozen=True)
class ImpressionRef:
    impression_id: str
    user_id: str            # from the impression row -- the ownership check's input
    session_id: str
    rank: int
    item_ids: list[str]
    outfit_fingerprint: str
    total_score: float
    is_exploration: bool

class ISuggestionLogRepository(ABC):
    ...
    @abstractmethod
    async def find_impression(self, *, session_id: str, rank: int) -> ImpressionRef | None:
        """MUST NEVER RAISE (port-wide contract). Returns None on not-found
        AND on any error -- the caller cannot distinguish, and must not try.
        Resolves on the (session_id, rank) UNIQUE constraint
        (suggestion_impressions_session_rank_unique, 013:126)."""
```

### 4. Regenerate — the exact mechanism (AC #5, raw ticket edge case #2)

SS-020's endpoint has **no** cache-bypass or pool-widening request parameter — the effort tier is resolved *server-side* from budget/routing state (`resolve_effort_tier_for_request`) and is not client-settable, and the narration cache is keyed on candidate *shape*, so it is not the thing that would repeat outfits anyway. Engine v2's novelty term (`engine_v2_novelty.py`) is **item-level and 30-day-windowed**; it makes a repeat mildly less likely, never impossible, and cannot react to a dismissal three seconds ago. The briefing's "it does have effort-tier and pool-size knobs" is true of `EffortTierParams` internally but **not** reachable from a request — so a client-supplied exclusion list is the mechanism, and it is new.

- Client accumulates every `outfit_fingerprint` it has *shown* (not merely dismissed — a card the user swiped right on should not come back either) in `outfit-ai.store.ts`, capped at 60, FIFO.
- "Regenerate" re-POSTs `/portfolio` with the same occasion and `exclude_fingerprints = [...]`.
- `OutfitPortfolioService` passes `frozenset(exclude_fingerprints[:60])` to `EngineV2.generate_portfolio(exclude_fingerprints=...)`; `engine_v2_portfolio.select_portfolio` drops any scored candidate whose `compute_outfit_fingerprint(item_ids)` is in the set **before** MMR selection (so diversity is computed over what actually remains, not over a set that then gets holes punched in it).
- If exclusion leaves fewer than the portfolio floor, the engine returns what it has with `limited_options=True` — the UI shows "That's every look we can build from your wardrobe right now" with a route to upload, **never** an empty deck and never a silent repeat.
- The exclusion set is cleared when `selectedOccasionKey` changes (a different occasion legitimately re-uses the same garments).
- Server-side belt-and-braces is explicitly **not** built here: `idx_suggestion_impressions_user_fingerprint` (`013:136-137`, created with the comment "SS-023 regenerate AC") exists and would support an automatic "exclude what we showed this user in the last N minutes" filter. Deferred to a backlog row rather than built, because it changes results for *every* caller including a fresh session, which is a personalisation-quality decision (`BL-077`'s territory), not a UI one.

### 5. Screen behaviour, occasions, tokens and copy

**Two-tap guarantee (AC #1).** Tap 1 = an occasion tile (which *also* immediately fires the request — selection and submission are the same gesture); tap 2 is not needed to reach results. The explicit "Get suggestions" CTA exists as a secondary affordance for re-submitting the already-selected occasion (and as the accessible, non-grid path), so the AC's "max 2 taps" holds with one tap to spare. A deep link (`/style?occasion=festival`) reaches results in **zero** taps by pre-selecting and auto-firing.

**Occasion grid is dynamic, from the registry — not `OCCASION_PILLS`.** Source: `useOccasionTaxonomy().topLevelOccasions` (`features/onboarding/onboarding.queries.ts:210-249`). The hardcoded 6-item `home.constants.ts:OCCASION_PILLS` list stays exactly where it is and is **not** reused here — it is a deliberately curated Home-tab subset with emoji that are not registry columns (see its own header comment). The Style tab shows the full active registry, so adding an occasion stays an `INSERT` with no code change.

- **Labels: render `occasions.label` (English) with no i18n lookup.** `occasions.labels_i18n` ships `'{}'` for every row (`BL-090`) — there are no translations to look up, and a lookup helper written now would be dead code that silently returns English anyway. This is the first screen where an untranslated regional-festival name is visible to a user, and this design states that explicitly rather than pretending otherwise. When `BL-090` is resolved, the change is localised to `OccasionGrid.tsx` + `onboarding.occasions.ts`'s label helper.
- **Badge colours: 4 families for 12 occasions is accepted as-is** (`BL-088`). `Badge`'s `OccasionKey` union is `'wedding' | 'office' | 'festival' | 'casual'` (`components/ui/Badge.tsx:3`), and `occasions.badge_color` is `NOT NULL` with a CHECK against exactly those four (SS-025), so `festival` and `party` render identically, as do several others. Do **not** attempt to widen the palette in this ticket — it needs a coordinated token + migration + release, and `BL-088` already tracks it. Pass `occasion={badgeColor(key)}` via the existing taxonomy hook; the neutral fallback covers the still-loading case by construction.
- **Loading/error/empty/stale states are all mandatory** (CLAUDE.md). The taxonomy hook already exposes `isLoading` / `isError` / `isStale` (last-known-good AsyncStorage cache) — surface `isStale` as a quiet notice, not a blocker.

**Styling rules.** NativeWind `className` only — no `StyleSheet.create`, no inline styles. `Text`/`View` from `components/ui/` (never React Native directly). `expo-image` for every thumbnail. Navigation via `router.push` (Expo Router). Deck list is small and fixed (3 cards) so neither `FlatList` nor `FlashList` is involved.

**Copy (fixed, use verbatim):**
- Occasion screen heading: `What's the occasion?`
- CTA: `Get suggestions`
- Loading: `Styling three looks for you…`
- Regenerate: `Not quite right — regenerate` (AC #5's own wording)
- Zero wardrobe items: heading `Add a few pieces first`, subtext `We need at least a top and a bottom to style a look.`, CTA `Add items` → `router.push('/wardrobe/upload')`
- Exhausted after regenerate: `That's every look we can build from your wardrobe right now`
- Accept confirmation: `Saved to your outfits`
- Dismiss: no toast (a swipe left is self-evident; a toast on every reject is noise)
- Already-saved (idempotent hit): `Already in your outfits`
- Backend unreachable / 5xx: `Couldn't reach the stylist. Try again in a moment.` with a retry button — every `fetch` wrapped in `try/catch` with a user-facing message (CLAUDE.md), never a bare rejection.
- Score badge: `{Math.round(total_score * 100)}% match` — `total_score` is `NUMERIC(6,5)` in `[0,1]` per `013:120`, so this is a percentage, not an arbitrary scale. Never render the raw float.
- Any rupee figure that appears (none in v1, but if a cost-per-wear surfaces on the accepted panel): `₹1,23,456` via `Intl.NumberFormat('en-IN', …)`, reusing `ItemDetailSheet`'s existing `formatIndianCurrency` — do not re-author it.
- Dates: `'en-IN'`, `Asia/Kolkata`.

**Analytics call sites (closes `BL-034`).** Confirmed against `docs/worklog/SS-020.md`: SS-020 wired **no** mobile analytics (backend-only ticket), so `BL-034`'s "first outfit suggestion reward hook needs mobile-side wiring" is genuinely still open and this is its natural home.
- `first_suggestion_viewed` — fired once when the first non-empty deck renders. Property shape is `Record<string, never>`; do not add an occasion property without extending `AnalyticsEventProperties` first.
- `first_outfit_saved` — fired on the first successful `saved` outcome.
- `outfit_shared` — `{ channel }` on a successful share.
- Fire-once semantics are per user, persisted via `lib/storage.ts`, not per app session — a "first ever" event that re-fires on every cold start is worse than not firing.

**Weather chip: not built.** SS-022 is `not started` (`docs/worklog/README.md:46`) and there is no weather module anywhere in `mobile/`. Per the raw ticket's own Status note, ship without it. `WeatherChip.tsx` is **not** created as a stub — an empty placeholder component is dead code SS-022 would replace wholesale. The layout leaves a slot above the CTA; that is all.

### 6. `wardrobe_item_wears.outfit_id` (BL-120) and Mark Worn's occasion (BL-121)

`BL-120` has now been deferred by SS-035, SS-038 and SS-020 in turn, each naming SS-023 as the owner (`engine_v2.py:41` says so in a source comment). This design closes it, and does so on a clear semantic line:

- **Swipe right = `saved`, not `worn`.** It writes `outfits` + `suggestion_outcomes(outcome_type='saved')` and **no** wear row. Conflating "I like this" with "I wore this" would corrupt `wear_count`, `cost_per_wear`, and Engine v2's own wear-recency novelty term — a data-integrity error, not a UX shortcut.
- **A separate explicit "Wore this today" action** on `AcceptedOutfitPanel` sends `outcome_type='worn'`, which writes one `wardrobe_item_wears` row per item with **`outfit_id` = the saved outfit** and **`occasion_key` = the outfit's normalised occasion** — the first and only writer `outfit_id` will ever have. It also writes `suggestion_outcomes(outcome_type='worn')`.
- Idempotency is free: `wardrobe_item_wears_one_per_day_per_occasion` (`015`, `UNIQUE NULLS NOT DISTINCT (item_id, worn_on, occasion_key)`) collapses a repeat tap, and `015`'s `BEFORE INSERT` normalisation trigger runs before the constraint is evaluated. Use `ON CONFLICT DO NOTHING` and report "Already logged for today", reusing SS-015's existing copy rather than inventing new wording.
- **`BL-121` becomes answerable but is not answered here.** Once this ships, an outfit carries its occasion and its wear rows carry `occasion_key`, so a future ticket *could* default one-tap "Mark Worn" (the wardrobe-item surface, SS-035) from the most recent suggestion session. That is a product decision about a different screen — out of scope, and `BL-121` stays open with a note that the data now exists.

This sub-feature is **cleanly separable**: it is one extra `Literal` value, one repository method and one button. If Open Question #1's estimate conversation lands on "cut something," cut this — but cut it explicitly and leave `BL-120` open with a fourth deferral, rather than half-building it.

### 7. Occasion write-boundary validation (BL-078 boundaries 4 and 6)

`BL-078`'s matrix names six occasion write boundaries; 4 (`outfits.occasion`), 5 (`social_posts.occasion`) and 6 (`suggestion_sessions.occasion`) had only the `008` `SECURITY DEFINER` trigger backstop, with no application-layer validation, because none had a writer. This ticket resolves 4 and 6:

- **Boundary 6 (`suggestion_sessions.occasion`) is already covered as of SS-020, and this design confirms rather than adds it.** `OutfitPortfolioService` resolves the raw request string through `OccasionNormalizer.get_registry(jwt) → .resolve(raw, snapshot)` and hands `OccasionStylingInput.key` to `EngineV2`, which is what `SuggestionSessionLog.occasion` is built from. So the value reaching the DB is already a registry-resolved canonical key, with the trigger as the second line of defence, not the only one.
- **Boundary 4 (`outfits.occasion`) is this ticket's to add.** `OutfitOutcomeService` must **not** trust any client-supplied occasion string, and the request model above deliberately has no `occasion` field. The occasion written to `outfits` is read from the *impression's own session row* (`suggestion_sessions.occasion`, already normalised) — server-derived, never client-asserted. That is stronger than "validate the input": there is no input to validate.
- If the session row's occasion is `NULL` or unresolvable (possible: `008`'s trigger normalises shape but "unknown occasion is a signal, not an error" per SS-012/SS-025), write it through unchanged and let the trigger's `occasion_log_unknown` path record it. Never reject the save because the occasion is unmodelled — the user's outfit is not the place to enforce taxonomy completeness.
- **Boundary 5 (`social_posts.occasion`) stays open**, unowned by this ticket. `BL-078` therefore does not fully close; it gets updated to "boundaries 4 and 6 covered by SS-023; boundary 5 awaits the social/OOTD ticket."

## Edge cases

Carried forward from the raw ticket:

- **Zero wardrobe items** — the CTA never calls `/portfolio`. `useWardrobeItemCountQuery` gates the screen; count `0` renders the "Add a few pieces first" `EmptyState` routing to `/wardrobe/upload` (SS-013). Cheap (`count: 'exact', head: true`, the existing helper in `wardrobe.service.ts`) and it prevents a guaranteed-empty billable request.
- **All 3 rejected → regenerate must not return the same 3** — handled structurally by §4's `exclude_fingerprints`, not by a cache flag.

Carried forward from SS-014/SS-015's deferred list (the raw ticket's Technical Note explicitly asks for these):

- **A wardrobe item is deleted while referenced by a saved outfit.** `outfits.item_ids` is a plain `UUID[]` with no FK (mirroring `013:129-132`'s deliberate posture), so the delete cannot cascade the outfit away or fail. The outfit still renders from `items_snapshot`, with the missing item shown as a greyed "no longer in your wardrobe" tile. `wardrobe_item_wears` rows *do* cascade (`006:22-24`, composite FK `ON DELETE CASCADE`) — that is SS-015's existing, correct behaviour and is not changed here.
- **The outfit itself is deleted while a `suggestion_outcomes` row points at it** — `outfit_id` is `ON DELETE SET NULL` (`013:154`), so the historical fact of the save survives. Nothing to build; noted so a reviewer doesn't expect cleanup code.
- **An item is deleted between the suggestion being generated and the swipe right.** The impression is unchanged (immutable history), so the save succeeds with a snapshot entry for an id that no longer resolves. This is correct: refusing the save would be worse, and the greyed-tile render already covers it. The `items_snapshot` build must therefore tolerate a wardrobe fetch returning fewer rows than `item_ids` has entries — write what resolved, leave the rest as `{item_id, missing: true}`.

New, from designing against the current codebase:

- **`session_id` is `None`** (session logging degraded). Cards still render; swipe right/left still work *visually* but no outcome can be recorded and no outfit is persisted. Show the deck, disable nothing, and on accept surface `Couldn't save that one — try regenerating.` Do not silently pretend it saved.
- **Double swipe-right / retried request on the same card** — `uq_outfits_user_fingerprint` collapses it; the service catches the unique violation, selects the existing row, and returns `already_saved: true` with the existing `outfit_id` (not an error). Mirrors `_is_dedupe_conflict`'s existing "success-already-recorded, not a failure" handling in `suggestion_log_repository.py:134-136`.
- **`(session_id, rank)` belongs to another user** — 404, no write, before anything else (§3). The cross-tenant case QA must actively attack.
- **`(session_id, rank)` is valid but the session has been retention-purged** (`purge_suggestion_logs`, 180 days) — impressions cascade with it, so `find_impression` returns `None` → 404. Correct; a 180-day-old open deck is not a real scenario, but the endpoint must not 500 on it.
- **`exclude_fingerprints` over the 60 cap** — truncate, never 422. A user who regenerates 25 times should get "we're out of looks," not a validation error.
- **Malformed / non-hex fingerprint in `exclude_fingerprints`** — it simply matches nothing. No validation, no error; a shape CHECK here would be a needless failure mode for a set whose only power is self-restriction.
- **Occasion registry still loading when a deep link arrives** — `resolveOccasion` normalises shape only and the raw param still matches a key it already equals (the behaviour `style.tsx:14-21` documents today). Preserve this; never crash, never blank.
- **Taxonomy query is `isStale`** (AsyncStorage last-known-good) — grid renders from cache with a quiet notice. Do **not** block suggestions on a fresh taxonomy fetch; the server re-resolves the occasion anyway.
- **The response contains 1 or 2 candidates instead of 3** (`limited_options`) — the deck renders what came back. There is no "3" anywhere in the contract; do not hardcode it in the deck component (`SuggestionSkeletonDeck`'s 3 skeletons are a visual constant, not a data assumption).
- **`rationale` is the rule-based degrade text, not LLM prose** (E0 tier, budget-denied, or the SS-020 latency timeout that `BL-139` records as the *expected* path for Sonnet-class models). The card must render it identically — no "AI unavailable" badge, no visual second-class treatment. Per SS-020's renegotiated AC this is a normal outcome, not a failure.
- **Cold-call latency is ~6s, not <4s** (`BL-139`, measured 16.2–16.7s for the LLM leg against a 6s router timeout). The skeleton deck must be designed for a genuinely multi-second wait — with an honest progress affordance, not a spinner that implies imminence — and the mutation needs a client timeout comfortably above the server's total deadline so the client never gives up on a request the server is about to answer.
- **Web vs. native gesture behaviour.** `react-native-gesture-handler` (v3) and `react-native-reanimated` (v4) are both already dependencies, but this repo is **web-first** and has no existing gesture-driven component to inherit a working configuration from. A drag gesture that works on native and not on web would fail AC #2 on the primary target. Mitigation: every swipe action must also be reachable from a plain accessible `Button`/`IconButton` (a ✓ / ✗ pair on the card) — which is required for accessibility regardless, and doubles as the guarantee that AC #2 is satisfiable even if the gesture layer degrades on one platform.
- **Never suggest white for `wedding_guest`** — enforced server-side in Engine v2's eligibility stage (`engine_v2_eligibility.py`, `HARD_EXCLUDED_COLOR_FAMILIES`). The UI must not re-implement or second-guess it; noted so a reviewer doesn't expect a client-side filter.

## Test plan

### Backend

**`backend/tests/test_outfit_outcome_service.py`** (new)
1. `saved` on a valid own impression inserts exactly one `outfits` row with `session_id`, `outfit_fingerprint`, `engine_version`, `effort_tier`, `items_snapshot` and `ai_generated=true` populated, and exactly one `suggestion_outcomes` row with `outcome_type='saved'` and matching `outfit_id`.
2. **Cross-tenant: an impression whose `user_id` differs from the JWT's returns 404 and performs ZERO writes** — asserted on the fakes' call logs, not just the status code. The single most important test in this ticket.
3. `find_impression` returning `None` (not found, purged, or repository error — indistinguishable by contract) → 404, no writes.
4. Repeat `saved` for the same `(user_id, fingerprint)` → `already_saved=True`, the pre-existing `outfit_id`, no second `outfits` row, no exception escaping.
5. `dismissed` writes a `suggestion_outcomes` row and **no** `outfits` row.
6. `worn` writes the outfit (or reuses it), one `wardrobe_item_wears` row per item with `outfit_id` set and `occasion_key` = the session's occasion, plus a `worn` outcome; a repeat on the same day is a no-op reporting "already logged" (§6 — skip this test if §6 is cut).
7. `occasion` written to `outfits` comes from the session row, never from the request — asserted by passing a service whose session row says `office` and confirming `office` is written regardless of anything the caller sent.
8. `log_outcome` failing (returns `None`) still returns `200` with `outcome_recorded=False` and does not roll back the `outfits` insert — a logging failure must not lose the user's outfit.

**`backend/tests/test_outfit_suggestions_router_outcome.py`** (new)
1. Missing / malformed / unsigned bearer token → `401` (real `get_current_user_id`, not the stub).
2. `rank=0` and negative rank → `422` (Pydantic `ge=1`), before any repository call.
3. `outcome_type='shuffled_away'` → `422` (not in the exposed `Literal`), proving the DB enum and the API surface are decoupled deliberately.
4. Happy path returns the documented `RecordOutcomeResponse` shape.
5. **Regression pin:** `/generate` still depends on `get_current_user_id_stub` and `/portfolio` still on `get_current_user_id` — this ticket must not drift either (`BL-052`'s scoping).

**`backend/tests/test_outfit_portfolio_service.py`** (extend)
1. Response now carries `session_id`, `occasion_key`, and per-item `rank` (1-based, contiguous) and `outfit_fingerprint` (64-hex).
2. Per-item `rank` equals the rank passed to `SuggestionImpressionLog` for the same candidate — the join key must be provably identical, not coincidentally aligned.
3. `exclude_fingerprints` is forwarded to `EngineV2.generate_portfolio`, truncated at 60, and an empty list is passed as `None`/empty without changing existing behaviour.
4. `session_id=None` (log repo degraded) still returns `200` with a full portfolio.

**`backend/tests/test_engine_v2_exclusion.py`** (new)
1. A candidate whose fingerprint is excluded never appears in the portfolio.
2. Exclusion happens before MMR: with the top-scoring candidate excluded, the returned set is the best *remaining* diverse set, not the original set minus one.
3. Excluding everything returns an empty portfolio with `limited_options=True`, not an exception.
4. `exclude_fingerprints=None` reproduces the pre-SS-023 output byte-for-byte on a fixed fixture (additive-widening proof).

**`backend/tests/test_db_schema.py`** (extend) — `outfits` has the six new columns with the documented types; `uq_outfits_user_fingerprint` exists and is partial; `user_id` is `NOT NULL`; `user_owns_outfits` is still `FOR ALL` (pin: this ticket deliberately does not change it); `trg_outfits_normalize_occasion` still exists and still fires on INSERT.

### Mobile

**`mobile/__tests__/app/(tabs)/style.test.tsx`** (rewrite)
1. Zero wardrobe items renders the upload CTA and **never** calls the suggestions service (asserted on the mocked service, not just the rendered text) — the raw ticket's edge case, as a negative assertion.
2. Tapping an occasion tile fires the request immediately — results reachable in one tap (AC #1).
3. A `?occasion=` deep link (including the legacy `wedding`/`date` keys) pre-selects the right tile via `resolveOccasion` — the behaviour `style.tsx` has today, preserved.
4. Skeleton deck renders while pending; error state renders the retry copy on a rejected mutation; empty portfolio renders the "every look" copy.
5. `first_suggestion_viewed` fires once on the first non-empty deck and does not re-fire on a second render or a regenerate.

**`mobile/__tests__/features/outfit-ai/components/OutfitCardDeck.test.tsx`**
1. Accept button → `useRecordOutcomeMutation` called with `outcome_type: 'saved'` and the card's `session_id`/`rank`; deck advances.
2. Reject button → `'dismissed'`; deck advances; no toast.
3. Every swipe action is reachable via an accessible button, not only a gesture (the web-first mitigation above) — assert by `accessibilityRole`/`testID`, since RNTL cannot exercise a real drag.
4. Exhausting the deck renders the regenerate CTA.

**`OutfitCard.test.tsx`** — score renders as `NN% match` (never a raw float); reasoning is collapsed by default and expands on press (AC #3); occasion badge uses `badgeColor(key)` and falls back to neutral while the taxonomy loads; a rule-based rationale renders identically to an LLM one (no degraded-visual treatment).

**`OutfitItemStack.test.tsx`** — renders one thumbnail per `item_ids` entry; an item id with no resolved image renders the "no longer in your wardrobe" placeholder rather than a broken image or a crash (the SS-014/SS-015 deleted-item edge case, at the UI layer).

**`OccasionGrid.test.tsx`** — tiles come from the registry hook, not `OCCASION_PILLS`; labels are `occasion.label` with no i18n lookup (`BL-090`); loading/error/stale states all render something; two occasions sharing a badge colour both render (`BL-088` is a visual constraint, not a bug to assert against).

**`outfit-ai.queries.test.tsx` / `outfit-ai.service.test.ts`** — the JWT is sent as `Authorization: Bearer`; the base URL comes from `constants/api.ts`; a non-2xx response produces a typed, user-facing error, never an unhandled rejection; a successful `saved` invalidates whatever outfit-list query key exists.

**`outfit-ai.store.test.ts`** — `dismissedFingerprints` accumulates shown *and* dismissed fingerprints, caps at 60 FIFO, and clears when `selectedOccasionKey` changes.

### Manual verification (recorded in the worklog, not asserted)

- One real end-to-end run against local `uvicorn` + the linked Supabase project: occasion → suggestions → swipe right → confirm a row in `outfits` and one in `suggestion_outcomes` with matching `outfit_id`, and confirm the `outfits.occasion` value equals the session's, not anything the client sent.
- Regenerate twice and confirm no fingerprint repeats across the three batches.
- **Swipe gesture on web** (`expo start --web`) and on at least one native target — this is the one AC that unit tests structurally cannot cover, and the platform where failure is most likely.
- `SELECT count(*) FROM outfits` is `0` before migration `020` is pushed (the precondition every tightening statement in it depends on).

## Open questions / blockers

**`Risk: high` → full lane. Items #1–#3 need explicit user sign-off before Developer starts.**

1. **[LOAD-BEARING] The estimate is wrong and the scope is materially larger than `2 pts` / `6h`.** The raw ticket is written as a UI ticket. In reality it carries: an additive migration on a shipped table with three dependent FKs, a new authenticated backend endpoint with a genuine cross-tenant auth boundary, two additive port methods, an additive Engine v2 kwarg, a new mobile domain folder with ~10 components, and a first-writer schema decision. None of it is avoidable — AC #2 ("swipe right saves outfit") cannot be met without a write path, and `suggestion_outcomes` has no client write policy by deliberate design. **Decision needed:** accept the larger single ticket (recommended — every proposed split leaves a half-ticket that satisfies zero ACs), or split the backend leg into its own `SS-0XX` via `/new-feature` and let SS-023 depend on it.
2. **[LOAD-BEARING] PNG export (AC #4) has no verified implementation path and this pass could not verify one.** `react-native-view-shot` is **not** a dependency (checked `mobile/package.json`), no repo pattern exists for client-side image composition, and this Architect pass has **no network access to verify its current web support** — asserting it from memory is exactly what `docs/OPERATOR_RULEBOOK.md` §E and `BL-001` forbid. Note the direct precedent: **SS-021's AC #4 ("shareable card image") is already sitting in `docs/worklog/README.md:40` as an open question proposed for deferral pending the user's sign-off.** These are the same decision and should be made once, for both tickets. Options: (a) **defer PNG export from both**, ship the share button with the text/deep-link fallback behind the `outfitCardExport` seam this design already specifies (recommended — smallest surface, `outfit_shared` analytics still fires, seam means no rework later); (b) spend a verification spike on a library choice (`react-native-view-shot` for native + a DOM-capture path for web) as its own ticket; (c) build it now on an unverified library. (c) is not recommended.
3. **[LOAD-BEARING] Migration `020` tightens `outfits.user_id` to `NOT NULL` and adds CHECK constraints to a table that has existed since `001` on production.** This is safe *only* because nothing has ever written the table. Every code path in the repo has been checked and none writes `outfits` — but Developer must confirm empirically (`SELECT count(*) FROM outfits` on the linked project) before push, and record the number in the worklog. If it is not zero, this migration must be re-designed as an expand/migrate/contract sequence, not tightened in place.
4. **The raw ticket's own premise is wrong** (`outfits` already exists; this ticket is its first writer, not its creator) and its Technical Notes should be read through this design's Scope restatement. Not blocking — flagged so a reviewer comparing ticket text to diff doesn't read the discrepancy as scope drift.
5. **SS-022 (weather) is `not started`** — shipping without the weather chip, per the raw ticket's own Status note. No stub component is created. Not blocking.
6. **`BL-139`'s latency reality** (cold LLM call measured 16.2–16.7s against a 6s router timeout, so the common cold path *degrades to rule-based rationale by design*) means this UI's "AI reasoning" will frequently be rule-generated prose. That is the renegotiated SS-020 AC, not a defect — but it is a product-quality fact worth knowing before this screen is user-tested, and it means the skeleton state carries more weight than a "fast API" design would assume.
7. **`BL-088` (4 badge colours for 12 occasions) and `BL-090` (empty `labels_i18n`) are both surfaced visibly by this screen and both accepted as-is**, per the briefing. Neither is fixed here; both rows get a note that SS-023 is the surface where they became user-visible.
8. **Server-side automatic anti-repetition is deferred** (§4's last bullet) — `idx_suggestion_impressions_user_fingerprint` exists for it, but it changes results for every caller, which is a personalisation-quality decision belonging with `BL-077`. New backlog row rather than built here.
9. **`mobile/types/supabase.ts` must be regenerated** after `020`. It is auto-generated (CLAUDE.md: "Supabase types from auto-generated `types/supabase.ts` ONLY") and a stale copy will silently type-check against a schema that no longer matches.

## Backlog deltas (for the orchestrator to apply to `docs/BACKLOG.md`)

Scanned rows were supplied by the orchestrator (no re-scan performed): `BL-034`, `BL-052`, `BL-078`, `BL-088`, `BL-090`, `BL-120`, `BL-121`.

**Resolve → Resolved (once Developer ships, not by this design pass alone):**
- `BL-034` — confirmed still open (SS-020's worklog shows a backend-only ticket with no mobile wiring); this ticket supplies the real `first_suggestion_viewed` / `first_outfit_saved` call sites.
- `BL-120` — closed by §6's `worn` path, the only writer `wardrobe_item_wears.outfit_id` will ever have. **Conditional:** if §6 is cut per Open Question #1, this stays Active with a fourth, explicit deferral note.

**Update note, stays Active:**
- `BL-078` — boundaries 4 (`outfits.occasion`, server-derived from the session row, §7) and 6 (`suggestion_sessions.occasion`, already covered by SS-020's `OccasionNormalizer` resolution, confirmed not added) are now application-layer covered. Boundary 5 (`social_posts.occasion`) remains open, unowned.
- `BL-121` — unchanged, but now *answerable*: outfits carry an occasion and wear rows carry `occasion_key` + `outfit_id`, so a future ticket can default Mark Worn's occasion from a suggestion session. Still a product decision on a different screen.
- `BL-088` — unchanged; note that SS-023's occasion grid is where the 4-colour collapse became user-visible, as predicted.
- `BL-090` — unchanged; note that SS-023 renders `occasions.label` (English) with no i18n lookup, deliberately and explicitly.
- `BL-052` — unchanged; `/generate` + `get_current_user_id_stub` untouched again, now pinned by a router regression test.
- `BL-139` — unchanged; reaffirmed as the reason this UI's loading state is designed for a multi-second wait and its rationale text is frequently rule-based.

**New rows (Active unless noted, next sequential IDs from whatever `docs/BACKLOG.md` currently holds):**
- `ai` | SS-023 / Architect — **server-side automatic anti-repetition** for suggestions: `idx_suggestion_impressions_user_fingerprint` was created by SS-033 explicitly for this, but SS-023 implements exclusion client-side only. A server-side "don't re-show what we showed in the last N minutes" filter changes results for every caller and belongs with `BL-077`'s quality eval.
- `infra` | SS-023 / Architect — **no verified client-side image-export path exists in this repo** (`react-native-view-shot` not installed, web support unverified, no network access during the Architect pass). Blocks AC #4 here and SS-021's AC #4 identically. Needs one verification spike that settles both. **Park only if Open Question #2 resolves to "defer"; otherwise Active.**
- `test` | SS-023 / Architect — **swipe-gesture behaviour on web is unverifiable by RNTL**; the accessible-button fallback is the mitigation, but real cross-platform gesture verification is manual-only in this repo and has no CI coverage. First gesture-driven component in the codebase.
- `schema` | SS-023 / Architect — **`suggestion_sessions.accepted_outfit_id` and `.suggestions` are both marked DEPRECATED** by `013:96-107` pending a CONTRACT migration (`BL-112`). SS-023 writes neither and uses `suggestion_outcomes` instead, as instructed — reaffirming that `BL-112`'s eventual drop has no new blocker from this ticket.

## Risk classification

`Risk: high` — **confirmed, and reinforced by findings the triage scan could not have seen.** Four independent one-way-door surfaces per `docs/OPERATOR_RULEBOOK.md` §C2: (1) a **migration** that tightens `NOT NULL` and adds CHECK constraints on a table that has been on production since `001` and carries three dependent foreign keys — safe only under an empirical precondition (`count = 0`) that must be verified, not assumed; (2) a **new authenticated write endpoint** whose impression lookup runs through a `service_role` client that *bypasses RLS entirely*, making the caller-vs-impression ownership comparison the only thing standing between this endpoint and a cross-tenant write primitive into the personalisation corpus; (3) the **first-ever writes** to `outfits`, `suggestion_outcomes` and `wardrobe_item_wears.outfit_id`, i.e. the moment three tables' data shapes stop being theoretical and start being expensive to change; (4) real user data at real auth behind a real JWT, on the product's primary surface. Nothing here argues for `med`. Full lane: every gate stays, and Developer must not start until Open Questions #1 (scope/estimate), #2 (PNG export path) and #3 (empty-table precondition) are explicitly answered by the user rather than defaulted.

