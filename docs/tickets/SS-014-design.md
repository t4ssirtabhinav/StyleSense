# SS-014 — Wardrobe Grid & Catalogue View — Design

## Scope restatement

This ticket replaces `app/(tabs)/wardrobe.tsx`'s SS-005/SS-013 empty-state placeholder with the real 2-column FlashList catalogue of a user's `wardrobe_items` — not a new route. It fetches the user's full item set once (React Query, `staleTime: 5 minutes`, per the ticket's own Technical Note), holds category/occasion/season/colour/search/sort state in Zustand, and derives the filtered/sorted array client-side via a pure selector rather than re-querying per filter change. Each `ItemCard` shows a 300px thumbnail on a neutral card, a category chip, a wear-count badge, and a tappable favourite heart; tapping a card opens a `BottomSheet` (`ItemDetailSheet`) with the full tag set and four actions — edit (reopens an editable tag form, reusing SS-013's `useSaveWardrobeItemTags`/`CategoryPicker`), delete (two-step confirm), mark worn (increments `wear_count`/`last_worn_at`), and favourite toggle. A sticky pill row filters by category group (All/Ethnic/Western/Footwear/Accessories/Favourites) with live per-category counts; occasion/season/colour filters and the 4 sort modes live behind a secondary filter sheet to avoid crowding the sticky row. A free-tier banner appears at ≥45 items (cap is 50, enforced elsewhere at upload time — this banner is informational only). This design also closes `BL-031`'s remaining half: the Home screen's wardrobe nudge becomes conditional on a real, cheap item-count query instead of always rendering (see "Home-nudge wiring" below).

A real architectural gap this ticket must close to work at all: no existing endpoint can resolve a *grid-scale* number of signed thumbnail URLs at once (SS-013's `GET /wardrobe/items/{id}/image-url` is single-item, and doesn't even serve `thumbnail_url`). This design adds one new small backend endpoint, `POST /wardrobe/items/image-urls`, to resolve this — flagged explicitly below since it's new backend surface the raw ticket doesn't mention, mirroring the posture SS-013 took for its own new endpoint (`BL-046`).

## Files to create/modify

**Backend (`backend/`) — new bulk image-URL resolution, only new backend surface this ticket adds:**
- `backend/routers/wardrobe.py` — **modify**. Add `POST /wardrobe/items/image-urls`: `BulkImageUrlsRequest { item_ids: list[str] }` (validated: 1–200 items, each a UUID, `field_validator` mirroring `RemoveBgRequest`'s pattern), `ImageUrlInfo { url: str, source: Literal["thumbnail", "original"] }`, `BulkImageUrlsResponse { urls: dict[str, ImageUrlInfo] }`. JWT-authed via `get_current_user_id` + `_extract_bearer_token` (same pattern as the existing single-item route). For each id: `thumbnail_url` present → `source="thumbnail"`; else `image_url` present → `source="original"`; else the id is silently omitted from the response map (not a per-id error — RLS already filters out ids the caller doesn't own, and this mirrors the single-item endpoint's "not an ownership oracle" precedent). Reuses `R2StorageClient.generate_presigned_get_url` (synchronous, local signing, no extra `asyncio.to_thread` needed) and `_IMAGE_URL_EXPIRY_SECONDS` (300s, same constant, not a new value).
- `backend/adapters/interfaces.py` — **modify**. Add `IWardrobeRepository.get_items_image_info_bulk(self, *, jwt: str, item_ids: list[str]) -> dict[str, dict[str, Any]]` — `SELECT id, image_url, image_clean_url, thumbnail_url, processing_status ... .in_("id", item_ids)`, RLS-scoped, keyed by id in the returned dict (ids not owned/found simply absent).
- `backend/adapters/wardrobe_repository.py` — **modify**. Implement the above.
- `backend/tests/test_wardrobe_router.py` — **modify**. Add bulk-endpoint cases.
- `backend/tests/test_wardrobe_repository.py` — **modify**. Add `get_items_image_info_bulk` cases.

**`features/wardrobe/` — modify (existing domain, extends SS-010/SS-013's):**
- `mobile/features/wardrobe/wardrobe.types.ts` — **modify**. Add `export type WardrobeItemRow = Tables<'wardrobe_items'>;` (imported from `../../types/supabase` — per CLAUDE.md, generated types only, never hand-duplicated columns). Add `CategoryGroup = 'ethnic' | 'western' | 'footwear' | 'accessories'`, `CategoryFilterValue = 'all' | CategoryGroup | 'favourites'`, `WardrobeSortOption = 'newest' | 'most_worn' | 'least_worn' | 'cost_per_wear'`, `WardrobeItemImageUrlInfo = { url: string; source: 'thumbnail' | 'original' }`, `WardrobeItemImageUrlsMap = Record<string, WardrobeItemImageUrlInfo>`, `WardrobeFilterState` shape (see wardrobe.store.ts below).
- `mobile/features/wardrobe/wardrobe.constants.ts` — **modify**. Add `CATEGORY_GROUPS: Record<WardrobeCategory, CategoryGroup>` (prefix-derived; `indo_western` → `'ethnic'`, see Concrete values/Open questions), `CATEGORY_FILTER_PILLS` (label + `CategoryFilterValue`, in order All/Ethnic/Western/Footwear/Accessories/Favourites), `SORT_OPTIONS` (label + `WardrobeSortOption`), `FREE_TIER_WARNING_THRESHOLD = 45`, `GRID_IMAGE_URLS_STALE_TIME_MS = 4 * 60 * 1000` (just under the 300s presign expiry), `WARDROBE_ITEMS_STALE_TIME_MS = 5 * 60 * 1000` (Technical Note's literal value), `SEARCH_DEBOUNCE_MS = 300`, `NO_ITEMS_IN_CATEGORY_HEADING`/`SUBTEXT`, `IMAGE_LOAD_FAILURE_MESSAGE`, `OFFLINE_UPLOAD_DISABLED_MESSAGE = 'No connection'`.
- `mobile/features/wardrobe/wardrobe.service.ts` — **modify**. Add `fetchWardrobeItems(): Promise<WardrobeItemRow[]>` (`supabase.from('wardrobe_items').select('*').order('created_at', {ascending: false})`), `fetchWardrobeItemCount(): Promise<number>` (`.select('id', {count: 'exact', head: true})`), `fetchWardrobeItemImageUrls(itemIds: string[], jwt: string): Promise<WardrobeItemImageUrlsMap>` (POST to the new bulk endpoint, same `EXPO_PUBLIC_BACKEND_URL` base as `removeBackground`/`tagItem`), `toggleWardrobeItemFavourite(itemId: string, isFavourite: boolean): Promise<void>`, `markWardrobeItemWorn(itemId: string, nextWearCount: number): Promise<void>` (caller supplies the incremented count — see Concrete values on why this isn't an atomic server-side increment), `deleteWardrobeItem(itemId: string): Promise<void>`.
- `mobile/features/wardrobe/wardrobe.queries.ts` — **modify**. Add exported key builders `wardrobeItemsQueryKey(userId)` / `wardrobeItemCountQueryKey(userId)` / `wardrobeItemImageUrlsQueryKey(userId)` (userId included per `auth.queries.ts`'s own `onboardingCompletedQueryKey` precedent, so a device account-switch can't serve stale cross-user cache). Add `useWardrobeItemsQuery(userId)`, `useWardrobeItemCountQuery(userId)`, `useWardrobeItemImageUrlsQuery(userId, itemIds, jwt)` (bulk, `enabled: itemIds.length > 0`), `useWardrobeItemImageUrlQuery(itemId, jwt)` (wraps SS-013's existing `fetchWardrobeItemImageUrl` service function in a `useQuery` for the first time — SS-013 only exposed the raw call), `useToggleWardrobeItemFavourite()`, `useMarkWardrobeItemWorn()`, `useDeleteWardrobeItem()` (each invalidates `wardrobeItemsQueryKey`/`wardrobeItemCountQueryKey` on success). **Also modify `useSaveWardrobeItemTags` (SS-013)**: add invalidation of `wardrobeItemsQueryKey`/`wardrobeItemCountQueryKey` on success — this query key didn't exist when SS-013 shipped, so a newly-saved item from the upload flow currently wouldn't appear in the grid without a manual pull-to-refresh; this retrofit is required for the two features to compose correctly. Update that file's stale header comment ("the one place a direct Supabase table write happens") since this ticket adds several more (favourite/worn/delete/list/count) — same established shape as the Edge Function/Realtime calls already in `wardrobe.service.ts`, not a new deviation.
- `mobile/features/wardrobe/wardrobe.store.ts` — **modify**. Add `useWardrobeFilterStore` (Zustand): `categoryFilter: CategoryFilterValue`, `occasionFilter: OccasionType | 'all'`, `seasonFilter: SeasonTag | 'all'`, `colorFilter: string | 'all'`, `search: string`, `sort: WardrobeSortOption`, setters for each, `reset()`. Kept separate from `useWardrobeUploadStore`/`useWardrobeBatchStore` — different lifecycle (filter state persists across the whole grid session, not per-upload-task).
- `mobile/features/wardrobe/wardrobe.selectors.ts` — **new**. Pure functions, no React/Zustand/Supabase imports (unit-testable in isolation, matches CLAUDE.md's "no `useEffect` for derived state — compute it directly during render", called via `useMemo` in the screen): `groupForCategory(category: WardrobeCategory | null): CategoryGroup | null`, `countsByCategoryFilter(items: WardrobeItemRow[]): Record<CategoryFilterValue, number>`, `selectFilteredSortedItems(items: WardrobeItemRow[], filters: WardrobeFilterState): WardrobeItemRow[]` (category/occasion/season/colour/search filters, then the 4 sort modes — see Concrete values for exact comparators).

**New components (`features/wardrobe/components/`), composing SS-008/SS-013 primitives — no new `components/ui/` primitives:**
- `mobile/features/wardrobe/components/ItemCard.tsx` — new. `React.memo`'d (Technical Note, literal). `Card variant="flat"` (neutral bg) + `expo-image` (thumbnail, `contentFit="contain"`, `cachePolicy="memory-disk"`), category `Badge` (neutral — no category colour tokens exist, humanized label or "Uncategorized" if `category` is null), wear-count `Text variant="caption"` ("Worn {n}×"), favourite `IconButton` (`heart`/`heart-outline`, top-right corner, optimistic toggle via `useToggleWardrobeItemFavourite`), and a processing overlay (see Edge cases) for any `processing_status !== 'bg_removed'`. `onError` on the image sets local retry state (see Edge cases).
- `mobile/features/wardrobe/components/WardrobeGrid.tsx` — new. Thin `@shopify/flash-list` `FlashList` wrapper: `numColumns={2}`, `data`/`renderItem={ItemCard}`, `keyExtractor={(item) => item.id}`, `refreshing`/`onRefresh` wired to a combined refetch (items + count + imageUrls queries). Loading/error/empty states are the *screen*'s job (`wardrobe.tsx`), not this component's — it only renders once there's a non-empty filtered array to show.
- `mobile/features/wardrobe/components/CategoryFilterBar.tsx` — new. Sticky horizontal row of `Badge` chips (`selected`/`onPress`), one per `CATEGORY_FILTER_PILLS` entry, label suffixed with the live count from `countsByCategoryFilter` (e.g. "Ethnic (12)").
- `mobile/features/wardrobe/components/SearchBar.tsx` — new. Thin wrapper around `Input variant="search"` with local debounce (`SEARCH_DEBOUNCE_MS`) before writing to `useWardrobeFilterStore.setSearch` — avoids re-deriving the filtered array on every keystroke.
- `mobile/features/wardrobe/components/WardrobeFilterSheet.tsx` — new. `AppBottomSheet` (SS-008 default snap points) opened via an `IconButton` (icon="options") next to `SearchBar`: occasion `Badge` row (single-select, `OCCASION_BADGE_COLOR_MAP` reused verbatim from SS-013 for the 4 coloured values, neutral for the other 8 — see `BL-008`), season `Badge` row (4 values), colour `Badge` row (**dynamically built** from the distinct non-null `color_primary` values present in the currently-loaded item set — no fixed palette exists for this free-text column, see Concrete values), and the 4 `SORT_OPTIONS` as a single-select `Badge` row. "Apply"/"Clear" actions write to `useWardrobeFilterStore`.
- `mobile/features/wardrobe/components/FreeTierBanner.tsx` — new. `Card` shown only when `!isPremium && itemCount >= FREE_TIER_WARNING_THRESHOLD`: "You're approaching the free plan's 50-item limit ({itemCount}/50). Upgrade to premium for unlimited items."
- `mobile/features/wardrobe/components/ItemDetailSheet.tsx` — new. `AppBottomSheet`, view mode: full image via `useWardrobeItemImageUrlQuery` (clean/original, fetched only when the sheet opens — not the grid's bulk thumbnail), all tags read-only (category humanized, subcategory, colours, pattern, fabric, occasion/season `Badge`s), wear count, last-worn date (`'en-IN'` locale, IST — CLAUDE.md), purchase info if present, and 4 actions: Edit (toggles local `mode: 'view' | 'edit'` state, renders `EditItemTagsForm`), Mark Worn (`useMarkWardrobeItemWorn`, optimistic), Favourite toggle (same mutation `ItemCard` uses), Delete (two-step: first tap arms a "Tap again to confirm" state, second tap calls `useDeleteWardrobeItem` then dismisses the sheet — no separate confirm-dialog component, kept as local state per the "no new `components/ui` primitives" precedent).
- `mobile/features/wardrobe/components/EditItemTagsForm.tsx` — new. Rendered inside `ItemDetailSheet` in edit mode: reuses SS-013's `CategoryPicker` (imported, not duplicated) for category, `Badge` multi-select rows for `occasionTags`/`seasonTags` (same pattern as SS-013's `ReviewStep`), `Input variant="text"` for subcategory/colorPrimary/colorSecondary/pattern/fabric. "Save" calls the existing, unmodified `useSaveWardrobeItemTags` (SS-013) with the edited draft.

**Shared (`hooks/`) — new, general-purpose, not wardrobe-specific:**
- `mobile/hooks/useNetworkStatus.ts` — new. Returns `{ isOffline: boolean }`. **Implementation API not pinned here** — Developer must verify against the currently-installed Expo SDK version's docs (per `mobile/AGENTS.md`'s standing instruction) whether `expo-network`'s own connectivity hook exists and covers this need before reaching for `@react-native-community/netinfo` as a new dependency; this design intentionally does not assert either API from memory (`[trained knowledge, not verified this session]` — see Open questions).

**Existing screen/component wiring:**
- `mobile/app/(tabs)/wardrobe.tsx` — **modify** (this ticket's core deliverable — replaces the SS-005/SS-013 placeholder, same route file, not a new one). Reads `useAuthStore((s) => s.session?.user.id)` and `.access_token`; calls `useWardrobeItemsQuery(userId)`, `usePlanTierQuery(userId)` (see below); derives `filteredItems` via `useMemo(() => selectFilteredSortedItems(items, filters), [items, filters])`; renders, in order: `CategoryFilterBar`, `SearchBar` + filter-sheet trigger, `FreeTierBanner` (conditional), then one of — loading (`Skeleton variant="card"` × 6 in a 2-col layout), error (reuses `EmptyState` with a "Couldn't load your wardrobe" heading + Retry `Button` calling `refetch()`), fully-empty (existing `EmptyState`, now gated on `items.length === 0` instead of unconditional — CTA unchanged, `router.push('/wardrobe/upload')`), filtered-empty (`EmptyState`, "No items in this category" + "Add item" CTA — distinct copy from fully-empty), or `WardrobeGrid`. A floating `IconButton` (icon="add", filled, bottom-right) always routes to `/wardrobe/upload` when there's ≥1 item already (the existing `EmptyState`'s CTA covers the 0-item case) — **not literally named in the AC list but required for the screen to be usable past the first item; flagged as an Architect addition**, disabled + `OFFLINE_UPLOAD_DISABLED_MESSAGE` caption when `useNetworkStatus().isOffline`.
- `mobile/features/home/components/WardrobeNudgeCard.tsx` — **modify** (closes `BL-031`'s remaining half). Calls `useWardrobeItemCountQuery(userId)`; renders `null` while loading, on error (fail-safe: never show "add your first item" to a user whose real count is simply unknown), and when `count > 0`. Otherwise renders unchanged. Bonus fix bundled in (no separate ticket needed): `onPress` now routes directly to `/wardrobe/upload` instead of `/wardrobe` — safe now that the destination exists, skips a redundant hop; only reachable when count is already known to be 0.
- `mobile/features/auth/auth.queries.ts` — **modify**. Add `usePlanTierQuery(userId)` wrapping the existing `fetchUserPlanTier` service function (same file layering as `useOnboardingCompletedQuery`) — needed by the free-tier banner and the floating add-button's gating logic (premium never shows the banner, still shows the add button).

**Tests:**
- `mobile/__tests__/features/wardrobe/wardrobe.selectors.test.ts` — new.
- `mobile/__tests__/features/wardrobe/components/ItemCard.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/WardrobeGrid.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/CategoryFilterBar.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/SearchBar.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/WardrobeFilterSheet.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/FreeTierBanner.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/ItemDetailSheet.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/EditItemTagsForm.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/wardrobe.store.test.ts` — **modify**. Add `useWardrobeFilterStore` cases.
- `mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx` — **modify**. Add new hook cases + `useSaveWardrobeItemTags`'s new invalidation case.
- `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` — **modify**. Add new raw-call cases.
- `mobile/__tests__/app/(tabs)/wardrobe.test.tsx` — **modify** (near-full rewrite): loading/error/fully-empty/filtered-empty/populated states, free-tier banner threshold, floating add-button routing + offline-disabled state.
- `mobile/__tests__/features/home/components/WardrobeNudgeCard.test.tsx` — **modify**. Conditional-rendering cases (loading/error/count=0/count>0), new `/wardrobe/upload` destination.
- `mobile/__tests__/features/auth/auth.queries.test.tsx` — **modify**. `usePlanTierQuery` case.
- `mobile/__tests__/hooks/useNetworkStatus.test.ts` — new.

**Explicitly not touched:** no `supabase/migrations/*.sql` (all columns already exist per `001_initial.sql`/`005_wardrobe_processing_status.sql`), no RLS policy change (existing `user_owns_wardrobe` policy already covers every new query/mutation), no new `components/ui/` primitives.

## Concrete values to use, not invent

**`WardrobeItemRow`**: `Tables<'wardrobe_items'>` from `mobile/types/supabase.ts` — do not hand-author a duplicate interface (CLAUDE.md: generated types only). Relevant columns: `id, category, subcategory, color_primary, color_secondary, pattern, fabric, occasion_tags, season_tags, brand, user_notes, is_favourite, wear_count, cost_per_wear, last_worn_at, created_at, processing_status, image_url, image_clean_url, thumbnail_url, purchase_price, purchase_date`.

**Category → group mapping** (prefix-derived from the 21-value `WardrobeCategory` union, transcribed verbatim from SS-013's design doc):
```
western_*      -> western
ethnic_*       -> ethnic
footwear_*     -> footwear
accessory_*    -> accessories
indo_western   -> ethnic   (Architect's call — see Open questions)
```

**Sort comparators** (`selectFilteredSortedItems`, all null-safe — see Edge cases):
- `newest` (default): `created_at` descending.
- `most_worn`: `wear_count` (treat `null` as `0`) descending.
- `least_worn`: `wear_count` (treat `null` as `0`) ascending — never-worn items (0) surface first, matching the label's plain-English meaning.
- `cost_per_wear`: ascending (lowest/best-value first — Architect's call, not pinned by the ticket, matches the common "cost-per-wear" UX convention); items with `cost_per_wear === null` (never worn, or no `purchase_price`) always sort **last**, regardless of direction.

**Free-tier banner threshold**: `FREE_TIER_WARNING_THRESHOLD = 45`, `FREE_TIER_WARDROBE_CAP = 50` (already defined, SS-010) — banner text: *"You're approaching the free plan's 50-item limit ({itemCount}/50). Upgrade to premium for unlimited items."* Never shown when `planTier` is `'premium'`/`'premium_annual'`.

**Bulk image-URL endpoint contract**: `POST /wardrobe/items/image-urls`, body `{"item_ids": string[]}` (1–200 UUIDs), response `{"urls": {"<id>": {"url": string, "source": "thumbnail" | "original"}}}`. Presign expiry 300s (`_IMAGE_URL_EXPIRY_SECONDS`, unchanged). Client-side: one call per `useWardrobeItemsQuery` success (all currently-loaded item ids at once — the free tier is capped at 50 and even a generous premium wardrobe fits comfortably under the 200-id endpoint cap; see Open questions for what happens past that), re-invalidated together with the items/count queries on pull-to-refresh, item delete, and item save (edit).

**`wear_count` increment is client-computed, not an atomic server-side increment**: `useMarkWardrobeItemWorn` reads the item's current `wear_count` from the already-cached `useWardrobeItemsQuery` data (no extra read) and writes `wear_count: current + 1, last_worn_at: new Date().toISOString()`. This is the same class of read-then-write race already logged as `BL-036`/`BL-066` (no atomic partial-update/increment without a Postgres RPC, deliberately not added here to stay migration-free) — noted as a third instance in the backlog delta below, not a new row.

**Processing-status overlay semantics** (correcting the raw ticket's own wording against the actually-shipped `wardrobe_processing_status` enum — same class of correction SS-013 made for the 20-vs-21 category count): the raw ticket's edge case says `bg_pending` means "still processing," but per SS-011/SS-013's design docs, `bg_pending` is BG-removal's **terminal failure fallback** (original image is final, nothing is in flight), while `uploaded`/`bg_processing` are the actually-in-progress states. This design ships the *correct* semantics: `uploaded`/`bg_processing` → dim scrim + `Text variant="caption"` "Processing…" overlay on the original image; `bg_pending` → original image with a small, non-progress caption "Background not removed" (no spinner/progress connotation — retry isn't SS-014's job, that's SS-013's `ProcessingStep`). `bg_removed` → no overlay, shows the real thumbnail.

**Colour filter values**: dynamically derived — `Array.from(new Set(items.map(i => i.color_primary).filter(Boolean)))` — not a fixed palette (no controlled vocabulary exists for `color_primary`/`color_secondary`, same class of gap as `BL-064`'s pattern/fabric note; see Backlog deltas).

**Search fields**: case-insensitive substring match against humanized `category` label (via SS-013's existing `WARDROBE_CATEGORIES` label lookup) + raw `category` value, `brand`, `user_notes` — matches the AC literally ("category, brand, and `user_notes`"), not `subcategory`/`fabric`/`pattern`.

## Edge cases

Carried forward from the raw ticket, plus ones surfaced designing against the real schema/enum:

- Items still processing (`uploaded`/`bg_processing`): original image + "Processing…" overlay (see Concrete values for the `bg_pending` correction — that state gets different, non-progress copy).
- No items match the filter: "No items in this category" + "Add item" CTA to `/wardrobe/upload` — distinct copy from the fully-empty-wardrobe state.
- Image load failure (a signed URL 404s/expires mid-session): `ItemCard`'s `expo-image` `onError` shows a placeholder icon + retry `IconButton` that invalidates `wardrobeItemImageUrlsQueryKey(userId)` (re-fetches fresh signed URLs for the whole visible set — simpler and cheap enough not to warrant a per-item retry mechanism).
- Offline: `useWardrobeItemsQuery`'s last-successful data serves from React Query's cache automatically (no special handling needed for this half); the floating add-button is disabled with the `OFFLINE_UPLOAD_DISABLED_MESSAGE` caption via `useNetworkStatus()`.
- **New: item with `category === null`** (SS-011 creates rows with `category=NULL`; tagging may still be pending/failed/flagged). `ItemCard` renders "Uncategorized" instead of a blank/crashing chip; such items are excluded from every category-group pill (Ethnic/Western/Footwear/Accessories) but still counted under "All" and (if `is_favourite`) "Favourites".
- **New: `cost_per_wear` is a `GENERATED` column** (`BL-004`) — never written directly by any mutation in this ticket (`useMarkWardrobeItemWorn` only writes `wear_count`/`last_worn_at`; Postgres recomputes `cost_per_wear` itself). The sort selector must read the recomputed value on the *next* fetch, not assume it updates optimistically in the local cache — the optimistic update for "mark worn" updates `wear_count`/`last_worn_at` only, leaving `cost_per_wear` stale-but-harmless until the next real fetch (it isn't shown as a standalone figure anywhere in this ticket's UI, only used for sorting).
- **New: delete has no undo/soft-delete** — the two-step confirm (see `ItemDetailSheet`) is the only safeguard; the underlying R2 objects (`original.jpg`/`clean.png`/`thumbnail.jpg`) are **not** cleaned up by this ticket's delete mutation (DB row only) — logged as a new backlog row, not fixed here (low urgency, no PII-exposure risk beyond what already existed while the row was live).
- **New: `indo_western`'s single-group assignment** (see Concrete values) means an item tagged `indo_western` never appears under the "Western" pill, only "Ethnic" — flagged as a real, if minor, product ambiguity in Open questions.
- **New: bulk image-URL endpoint's 200-id cap** — not expected to bind pre-launch (free tier caps at 50; no confirmed premium user base yet) but not built to paginate past it either — flagged, not fixed.
- Never suggest white for `wedding_guest` (CLAUDE.md India rule) — not applicable here (this screen catalogues/edits existing items, doesn't suggest outfits); noted so a reviewer doesn't expect it in this ticket's scope.

## Test plan

**`wardrobe.selectors.test.ts`:**
1. `groupForCategory` maps every one of the 21 `WardrobeCategory` values to the correct group; `null` category returns `null`.
2. `countsByCategoryFilter` returns correct counts per pill, including "All" = total and "Favourites" = `is_favourite` count independent of category group.
3. `selectFilteredSortedItems`: category filter, occasion filter, season filter, colour filter, and search each independently narrow the result set correctly; combined filters AND together.
4. Each of the 4 sort modes produces the expected order, including `cost_per_wear`'s null-last behaviour and `least_worn`'s 0-first behaviour.

**`ItemCard.test.tsx`:**
1. Renders category chip label (humanized) or "Uncategorized" when `category` is null.
2. Renders wear-count text matching `wear_count`.
3. Tapping the favourite heart calls `useToggleWardrobeItemFavourite` with the toggled value.
4. `processing_status='uploaded'`/`'bg_processing'` renders the "Processing…" overlay; `'bg_pending'` renders "Background not removed" (no progress copy); `'bg_removed'` renders neither.
5. Image `onError` renders the retry icon; pressing it invalidates the bulk image-urls query key.

**`WardrobeGrid.test.tsx`:**
1. Renders a `FlashList` with `numColumns={2}` and one `ItemCard` per item.
2. Pull-to-refresh (`onRefresh`) triggers the combined refetch.

**`CategoryFilterBar.test.tsx`:**
1. Renders all 6 pills with correct live counts.
2. Selecting a pill updates `useWardrobeFilterStore.categoryFilter` and visually marks it `selected`.

**`SearchBar.test.tsx`:**
1. Typed input is debounced (`SEARCH_DEBOUNCE_MS`, fake timers) before `useWardrobeFilterStore.setSearch` is called.
2. Clear button resets both local text and store state immediately (not debounced).

**`WardrobeFilterSheet.test.tsx`:**
1. Colour row options match the distinct `color_primary` values passed in (dynamic, not hardcoded).
2. Selecting an occasion/season/sort option and pressing "Apply" writes to the store; "Clear" resets to defaults.

**`FreeTierBanner.test.tsx`:**
1. Hidden below 45 items; visible at 45+ for `planTier='free'`.
2. Hidden at any count for `planTier='premium'`/`'premium_annual'`.

**`ItemDetailSheet.test.tsx`:**
1. Renders full tag set read-only in view mode; fetches the full image via `useWardrobeItemImageUrlQuery`, not the grid's thumbnail.
2. "Edit" swaps to `EditItemTagsForm`.
3. "Mark Worn" calls `useMarkWardrobeItemWorn` with `wear_count + 1`.
4. First "Delete" tap arms the confirm state without deleting; second tap calls `useDeleteWardrobeItem` and dismisses.
5. Favourite toggle here uses the same mutation `ItemCard` uses (shared cache, no divergent state).

**`EditItemTagsForm.test.tsx`:**
1. Renders `CategoryPicker` (imported from SS-013, not duplicated) and editable fields pre-filled from the item's current tags.
2. "Save" calls `useSaveWardrobeItemTags` with the edited draft.

**`wardrobe.store.test.ts`** (additions): filter store setters/`reset()` cases, one per field.

**`wardrobe.queries.test.tsx`** (additions):
1. `useWardrobeItemsQuery`/`useWardrobeItemCountQuery` call the right service functions, keyed by `userId`.
2. `useWardrobeItemImageUrlsQuery` calls the bulk service function with all provided ids; disabled when `itemIds` is empty.
3. `useToggleWardrobeItemFavourite`/`useMarkWardrobeItemWorn`/`useDeleteWardrobeItem` each invalidate `wardrobeItemsQueryKey`/`wardrobeItemCountQueryKey` on success.
4. `useSaveWardrobeItemTags` (SS-013, retrofit) now also invalidates those same two keys on success.

**`wardrobe.service.test.ts`** (additions): each new raw-call function hits the right endpoint/table with the right payload (mirrors SS-013's existing test shapes for `removeBackground`/`tagItem`).

**`app/(tabs)/wardrobe.test.tsx`** (rewrite):
1. Loading state renders skeletons, not the grid or empty state.
2. Error state renders a Retry button that calls `refetch()`.
3. `items.length === 0` renders the existing fully-empty `EmptyState` (heading/subtext/CTA unchanged from today).
4. Non-empty `items` but empty `filteredItems` renders the filtered-empty state with distinct copy.
5. Populated state renders `CategoryFilterBar` + `WardrobeGrid`.
6. `FreeTierBanner` appears/disappears per count + plan tier.
7. Floating add-button routes to `/wardrobe/upload`; disabled + captioned when offline.

**`WardrobeNudgeCard.test.tsx`** (rewrite): loading → null; error → null; `count=0` → renders card, CTA routes to `/wardrobe/upload`; `count>0` → null.

**`auth.queries.test.tsx`** (addition): `usePlanTierQuery` calls `fetchUserPlanTier` keyed by `userId`.

**`useNetworkStatus.test.ts`**: mocked online/offline transitions toggle `isOffline` correctly (exact mock target depends on which API Developer verifies is available — see Open questions).

**`test_wardrobe_router.py`** (additions): bulk endpoint returns URLs only for owned/found ids (mixed present/absent), rejects >200 ids with 422, rejects malformed UUIDs with 422.

**`test_wardrobe_repository.py`** (additions): `get_items_image_info_bulk` returns a dict keyed by id, RLS-scoped.

**Not automatable this pass (manual/device verification):**
- Real 60fps scroll measurement with 50-100 real items on a physical mid-range Android device (compounds `BL-013`, no device/LAN access in this pipeline) — FlashList's virtualization is the mechanism, not something this test suite can measure frame timing for.
- BottomSheet Android device-matrix behaviour for `ItemDetailSheet`/`WardrobeFilterSheet` (compounds `BL-010`).

## Open questions / blockers — RESOLVED (user decision, 2026-07-26)

1. **New backend endpoint — DECIDED: proceed.** `POST /wardrobe/items/image-urls` is authorized in this ticket's scope, as specified above. Same posture as SS-013's `BL-046`.
2. **`useNetworkStatus`'s underlying API — unchanged, not a user decision.** Developer must still verify against the installed Expo SDK (per `mobile/AGENTS.md`) whether `expo-network` exposes a connectivity hook before adding `@react-native-community/netinfo`.
3. **`indo_western`'s category-group assignment — Architect's call stands (Ethnic only).** No objection raised; proceed as designed.
4. **`cost_per_wear` sort direction — Architect's call stands (ascending = best value first).** No objection raised; proceed as designed.
5. **Floating "add item" button — DECIDED: include it**, as designed (routes to `/wardrobe/upload`, disabled + captioned when offline).

All decisions made directly by the user — see `docs/worklog/SS-014.md` Architect entry addendum.

## Backlog deltas

Moved to **Resolved** in `docs/BACKLOG.md`:
- `BL-031` (infra) — **fully resolved by this design.** The Home-nudge-hiding half (the only remaining half after SS-013 closed the Wardrobe-tab-CTA half) is specified in this doc's "Home-nudge wiring" (`WardrobeNudgeCard.tsx` modification, gated on `useWardrobeItemCountQuery`). Both halves of the original row are now closed.

Reaffirmed, not resolved (per the handed-to-me instruction):
- `BL-008` (tokens, occasion colour gap) — reaffirmed. This ticket's occasion filter chips and `ItemDetailSheet`'s occasion `Badge`s are the latest consumers hitting the same 4-of-12-coloured gap; ships neutral for the other 8, same accepted pattern as SS-004/SS-005/SS-013, reusing SS-013's `OCCASION_BADGE_COLOR_MAP` verbatim (no new colour invented).

Clarifying notes appended to existing Active rows (not moved, not duplicated):
- `BL-036` (schema, read-then-write race) — noted a third instance: `useMarkWardrobeItemWorn`'s client-computed `wear_count` increment shares the same no-atomic-partial-update-without-an-RPC gap as `style_preferences` (BL-036) and `ai_tags` (BL-066). Accepted for the same reason (low real-world concurrent-write likelihood for a single user's own wardrobe), not fixed here.
- `BL-064` (ai, no controlled vocabulary for pattern/fabric) — noted that `color_primary`/`color_secondary` are the same shape of gap (free `TEXT`, Gemini-supplied, no enum) — surfaced concretely by this ticket's colour filter having to derive its options dynamically rather than from a fixed palette.

New row added to **Parked** (tag `infra`):
- `BL-068` — Deleting a `wardrobe_items` row (this ticket's delete action) does not clean up its R2 objects (`original.jpg`/`clean.png`/`thumbnail.jpg`), leaving orphaned storage. Low urgency (storage cost only, no ongoing PII exposure beyond what already existed while the item was live); revisit alongside any future storage-cost/cleanup pass, not urgent pre-launch.

## Risk: med

Justification: this is primarily frontend composition (grid/filter/sort/search/detail-sheet UI) over already-existing columns — no schema/migration, no RLS policy change (existing `user_owns_wardrobe` policy already covers every new read/write path), no secrets, no payments, no auth changes. It does add one new backend REST endpoint (`POST /wardrobe/items/image-urls`) and three new direct-write mutations (favourite/mark-worn/delete) against a user's own already-existing rows — none of these are a one-way door per `OPERATOR_RULEBOOK.md` §C2 (the new endpoint is read-only/non-destructive; the delete mutation is destructive but scoped to the user's own data, not systemic, cross-user, or security/money-relevant, and gated behind an explicit two-step confirm). Classified `med` rather than `low` specifically because of the new backend surface (Open question #1, same posture as SS-013's `BL-046`) and delete's irreversibility — both warrant a quick human look, more friction than a pure `low`-risk placeholder/copy ticket, but neither reaches `high`'s auth/payments/schema/RLS/secrets/external-facing bar. Fast lane (architect→developer→qa auto-chain), consolidated human review at the PR — but Open questions #1–#5 above should be answered before/at Developer kickoff, not silently assumed.
