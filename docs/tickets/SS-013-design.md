# SS-013 — Wardrobe Item Upload Flow UI (Single + Bulk) — Design

## Scope restatement

This ticket builds the 3-step mobile upload UX (Capture → Processing → Review & Confirm) that turns SS-010/SS-011/SS-012's already-shipped backend pipeline into something a user can actually reach and use — it is pure `features/wardrobe/` UI composition, no new backend routes, no schema changes. **Capture** opens `expo-camera` (rear default, front toggle) or `expo-image-picker` (1-10 image multi-select gallery), with explicit permission-request copy and a settings-redirect on denial, plus new UI copy telling users to photograph one garment at a time (per `BL-057`, accepted-for-MVP). **Processing** drives SS-010's upload (`useUploadWardrobeItem`) followed by, per item, `POST /wardrobe/remove-bg` then `POST /wardrobe/tag` **sequentially against the same `item_id`** (the exact call contract SS-011's design doc pins down as `BL-041`'s resolution — this ticket must not invent a combined endpoint), with a `Skeleton`-driven shimmer and a Supabase Realtime subscription on `wardrobe_items` (`id=eq.{item_id}`) combining SS-012's documented readiness signal (`processing_status='bg_removed'` AND `ai_tags.tagging.status='tagged'`) to know when to advance. **Review & Confirm** renders the BG-removed cutout with every AI tag as an editable chip (`Badge`), a `BottomSheet`-driven category dropdown (all 21 `wardrobe_category` values, not the raw ticket's stated 20 — SS-012's design already corrected this), one-tap "Looks Good!" accept, and batch sequential progress (`1/10`, `2/10`...). This ticket also gives the Wardrobe tab's existing empty-state "Add your first item" CTA (`BL-031`) a real navigable destination.

## Files to create/modify

**New route:**
- `mobile/app/wardrobe/upload.tsx` — new. Expo Router screen hosting the 3-step flow (a local step state machine, not 3 separate routes — cancel/back semantics are simpler as one screen than as a stack). Accepts no route params; always starts at Capture.

**`features/wardrobe/` — new files (existing domain, extends SS-010's):**
- `mobile/features/wardrobe/wardrobe.types.ts` — **modify**. Add `UploadFlowStep = 'capture' | 'processing' | 'review'`, `WardrobeCategory` (verbatim 21-value union, transcribed from SS-012's design doc — see Concrete values), `OccasionType` (12-value union), `SeasonTag`, `GarmentTagsDraft` (the editable-in-review shape: `category`, `subcategory`, `colorPrimary`, `colorSecondary`, `pattern`, `fabric`, `occasionTags: OccasionType[]`, `seasonTags: SeasonTag[]`, `confidence`, `alternatives?`, `contentFlag`, `containsPerson`), `BatchItemState` (`{ taskId, itemId?, localUri, source, status: 'queued'|'uploading'|'removing_bg'|'tagging'|'ready'|'review'|'saved'|'failed', tags?: GarmentTagsDraft, error?: string }`).
- `mobile/features/wardrobe/wardrobe.constants.ts` — **modify**. Add `WARDROBE_CATEGORIES` (21-value array, label + value, for the `BottomSheet` searchable list), `OCCASION_TYPES`, `SEASON_TAGS`, `MAX_BATCH_SIZE = 10`, `REALTIME_CHANNEL_PREFIX = 'wardrobe_item_'`, `SLOW_NETWORK_HINT_DELAY_MS = 10000` (AC: "may take longer on slow connections" hint after 10s).
- `mobile/features/wardrobe/wardrobe.service.ts` — **modify**. Add `removeBackground(itemId: string, jwt: string): Promise<void>` (`POST /wardrobe/remove-bg`, expects `202`), `tagItem(itemId: string, jwt: string): Promise<void>` (`POST /wardrobe/tag`, expects `202`), `subscribeToItemUpdates(itemId: string, onUpdate: (row: WardrobeItemRow) => void): () => void` (thin wrapper around `supabase.channel(...).on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'wardrobe_items', filter: \`id=eq.${itemId}\` }, ...)`, returns an unsubscribe function). Both REST calls use `constants/api.ts`'s base URL, never a hardcoded host (CLAUDE.md).
- `mobile/features/wardrobe/wardrobe.queries.ts` — **modify**. Add `useProcessWardrobeItem()` — a mutation hook that, for one already-uploaded item (`itemId` from `useUploadWardrobeItem`'s result), calls `removeBackground` then `tagItem` sequentially and exposes a `status` derived from the Realtime subscription (wired via `subscribeToItemUpdates` inside a `useEffect` in the *screen*, not the hook itself — hooks in this file don't hold subscriptions per CLAUDE.md's "no `useEffect` for derived state" convention translated to "subscriptions live where they're consumed"; the *screen* owns the subscription lifecycle, the hook only exposes the two REST calls). Add `useSaveWardrobeItemTags()` — a mutation wrapping a direct RLS-scoped `supabase.from('wardrobe_items').update({...editedTags}).eq('id', itemId)` call for the "Looks Good!"/edited-tags save (this is the one place in this screen a direct Supabase table write happens — everything else routes through the FastAPI endpoints; flagged explicitly in Open questions since CLAUDE.md's "no direct Supabase calls in components" rule is satisfied — this lives in `.queries.ts` — but it's worth naming that this is a plain table `UPDATE`, not a `.service.ts`-wrapped call, mirroring SS-007's `patchStylePreferences` precedent for partial-field saves).
- `mobile/features/wardrobe/wardrobe.store.ts` — **modify**. Add `useWardrobeBatchStore` (Zustand): holds `items: BatchItemState[]`, `currentIndex: number`, actions `initBatch(sources)`, `updateItemStatus(taskId, status)`, `updateItemTags(taskId, tags)`, `advanceToNext()`, `reset()`. Kept separate from SS-010's existing `useWardrobeUploadStore` (upload-progress-only) rather than folding batch/processing state into it — different lifecycle (upload store's tasks end at "uploaded", this store's tasks continue through BG-removal/tagging/review/save).

**New components (`features/wardrobe/components/`, composing SS-008 primitives — no new `components/ui/` primitives per the ticket's own Status note):**
- `mobile/features/wardrobe/components/CaptureStep.tsx` — new. Full-screen `expo-camera` `CameraView` (rear default, `IconButton` to flip), a "Gallery" `Button` opening `expo-image-picker`'s `launchImageLibraryAsync({ allowsMultipleSelection: true, selectionLimit: 10 })`, and a persistent `Text variant="caption"` banner: **"Tip: photograph one item at a time for the best results"** (the `BL-057` UI-copy requirement). Permission handling: `useCameraPermissions()`/`useMediaLibraryPermissions()` from `expo-camera`/`expo-image-picker`; on denial, renders an explanatory `Card` with a `Button` labelled "Open Settings" calling `Linking.openSettings()`.
- `mobile/features/wardrobe/components/ProcessingStep.tsx` — new. `Skeleton variant="card"` shimmer overlay, status text driven by `BatchItemState.status` (`"Removing background..."` → `"Analysing your item..."`), a rotating `Text variant="caption"` tip (styling/organization tips, static array, no new content dependency), the slow-network hint after `SLOW_NETWORK_HINT_DELAY_MS`, and — for batch — a `Text` showing `"{currentIndex + 1}/{items.length}"`.
- `mobile/features/wardrobe/components/ReviewStep.tsx` — new. `Card` with the `clean.png` cutout (`expo-image`, signed-GET-URL resolution — see Open questions, `BL-046` is still unresolved for the read path), editable `Badge` chips for `occasionTags`/`seasonTags` (multi-select, `selected` prop toggled), text-style edit affordances for `colorPrimary`/`colorSecondary`/`pattern`/`fabric`/`subcategory` (plain `Input variant="text"`, not a new component), a `CategoryPicker` (below) for `category`, a low-confidence banner (`confidence < 0.7` or `contentFlag !== 'ok'` or `containsPerson`) worded per-cause, an `alternatives` picker (`Badge` row) shown only when present, and two primary actions: "Looks Good!" (`Button variant="primary"`, calls `useSaveWardrobeItemTags`) and an implicit "edit" path (chips are directly interactive, no separate edit-mode toggle — simpler state machine, matches the AC's "editable chips" wording literally).
- `mobile/features/wardrobe/components/CategoryPicker.tsx` — new. Thin wrapper: `BottomSheet` (SS-008's `AppBottomSheetRef.present()`) containing an `Input variant="search"` (filter-as-you-type) over the 21-value `WARDROBE_CATEGORIES` list, each rendered as a pressable row; selecting one calls `onSelect(category)` and dismisses. Satisfies the Technical Note's "BottomSheet with a searchable list for the 20 [sic — 21] categories" literally.
- `mobile/features/wardrobe/components/BatchSummaryToast.tsx` — new. End-of-batch summary: success count, failure count (AC: "Batch with one failure: continue the remaining items, show a failure count at the end"), two `Button`s — "Add another" (resets the store, returns to Capture) / "View wardrobe" (`router.push('/(tabs)/wardrobe')`).

**Existing screen wiring:**
- `mobile/app/(tabs)/wardrobe.tsx` — **modify**. The empty-state "Add your first item" CTA's `onPress` changes from a no-op/placeholder to `router.push('/wardrobe/upload')`. This is the entire `BL-031` half this ticket owns — no other change to this file (item-count-based nudge-hiding is SS-014's job, not touched here).

**Tests:**
- `mobile/__tests__/features/wardrobe/components/CaptureStep.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/ProcessingStep.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/ReviewStep.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/CategoryPicker.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/BatchSummaryToast.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/wardrobe.store.test.ts` — **modify**. Add `useWardrobeBatchStore` cases.
- `mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx` — **modify**. Add `useProcessWardrobeItem`/`useSaveWardrobeItemTags` cases.
- `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` — **modify**. Add `removeBackground`/`tagItem`/`subscribeToItemUpdates` cases.
- `mobile/__tests__/app/wardrobe/upload.test.tsx` — new. Screen-level integration smoke test (step transitions, cancel-at-any-step).
- `mobile/__tests__/app/(tabs)/wardrobe.test.tsx` — **modify**. Assert the CTA now navigates to `/wardrobe/upload`.

**Explicitly not touched:** no `backend/` files, no `supabase/migrations/*.sql`, no new `components/ui/` primitives (per the ticket's own Status note — `BottomSheet`/`Badge`/`Skeleton` are composed, not extended).

## Concrete values to use, not invent

**`WARDROBE_CATEGORIES` — transcribed verbatim from SS-012's design doc (which itself transcribed from `supabase/migrations/001_initial.sql` lines 7–14), 21 values, not the raw ticket's stated 20:**
```
western_top, western_bottom, western_dress, western_outerwear,
ethnic_kurta, ethnic_saree, ethnic_lehenga, ethnic_anarkali,
ethnic_salwar_kameez, ethnic_dupatta, ethnic_sherwani, indo_western,
footwear_formal, footwear_casual, footwear_ethnic, footwear_sports,
accessory_bag, accessory_jewellery, accessory_watch,
accessory_belt, accessory_scarf
```

**`OCCASION_TYPES` — verbatim from `001_initial.sql`, same 12 values SS-012 validates against:**
```
office, casual, date_night, wedding_guest, festival, puja,
party, travel, workout, beach, formal_event, college
```

**`SEASON_TAGS`** = `['summer', 'winter', 'monsoon', 'all']` (matches SS-012's `SeasonTag` literal).

**Readiness signal (verbatim from SS-012's design doc's "Client contract for SS-013" — do not invent a different combination):** an item is fully ready to move from Processing → Review when `processing_status === 'bg_removed'` **AND** `ai_tags.tagging.status === 'tagged'` (or `'flagged'` — see Edge cases below, flagged results still need review, they don't retry automatically). Both signals arrive via the same Realtime `UPDATE` subscription on `wardrobe_items` (`id=eq.{item_id}`) — SS-011's migration already added this table to the `supabase_realtime` publication, so no new Realtime setup is needed.

**Call sequencing (verbatim from SS-011's design doc, `BL-041`'s resolution — the load-bearing contract this ticket must follow exactly):** `POST /wardrobe/remove-bg` first (creates the `wardrobe_items` row, per SS-011), **then** `POST /wardrobe/tag` second, against the same `item_id`, sequentially — never in parallel, never a combined endpoint. `useProcessWardrobeItem` calls them one after another, `await`ing `remove-bg`'s `202` before firing `tag`'s request (both endpoints dispatch async background work server-side and return `202` immediately — the sequencing here is about request order, not about waiting for each to *finish* server-side; the Realtime subscription is what actually signals completion of each stage).

**Which image renders in Review:** `clean.png` (SS-011's BG-removed output) — but if `processing_status` never reached `'bg_removed'` (BG removal failed, `bg_pending`), fall back to rendering `original.jpg` with a small "background not removed" note rather than blocking Review entirely (an item can still be tagged and saved even if BG removal failed — the two pipelines are independent per SS-012's own design). **Reading these images back is `BL-046`, still unresolved** — see Open questions; this design does not invent a resolution.

**Category dropdown mechanism:** `BottomSheet` (SS-008's default `snapPoints = ['30%', '60%', '90%']`, no override needed for a scrollable 21-row list) + `Input variant="search"` for filter-as-you-type, per the Technical Note.

**Editable chips:** `Badge` with `selected` toggled for multi-select fields (`occasionTags`, `seasonTags`); `Badge`'s `occasion` colour prop is used only for the 4 colour-mapped occasions BL-008 already ships (`wedding_guest`≈`wedding`, `office`, `festival`, `casual` — note `wedding_guest` vs. `wedding` key mismatch, resolved by mapping `wedding_guest → 'wedding'` in the chip's colour lookup, all other 8 occasion values render neutral per BL-008's still-open gap, not invented here).

**Batch size:** `MAX_BATCH_SIZE = 10`, matching `expo-image-picker`'s `selectionLimit: 10` (AC: "1-10 images in a single session").

**Confidence/flag thresholds (reused verbatim from SS-012, not re-derived):** `confidence < 0.7` → low-confidence banner; `contentFlag !== 'ok'` → moderation banner (`'not_clothing'` → "Doesn't look like clothing" per SS-012's own edge case copy; `'nsfw'`/`'other'` → generic "couldn't process this image" without exposing raw moderation internals); `containsPerson === true` → "Try a flat-lay or mannequin shot for best results" nudge (SS-012's own documented intent for this flag).

## Edge cases

Carried forward from the raw ticket, plus SS-013-specific ones surfaced designing against the real backend contract:

- Camera permission denied permanently: "Open Settings" `Button` → `Linking.openSettings()`. (AC, `expo-camera`'s `useCameraPermissions()` exposes `canAskAgain` to distinguish "ask again" from "denied forever, only Settings can fix it.")
- Gallery/media-library permission denied: same pattern via `expo-image-picker`'s permission hook.
- Processing fails (BG-removal `bg_pending` or tagging `status='failed'`): `ProcessingStep` shows a retry `Button` that re-invokes the failed stage's endpoint only (not both — e.g. if `remove-bg` succeeded but `tag` failed, retry only re-calls `POST /wardrobe/tag` against the existing `item_id`, both endpoints are idempotent upserts/updates per SS-011/012's design), plus a "skip for now, tag manually" path that jumps straight to Review with empty/default tags (AC: "keep the original, allow manual tagging").
- User closes the app during processing: on next app open, `wardrobe.tsx` (or a resume check the store exposes) should detect any `BatchItemState` left in a non-terminal status and either re-subscribe to Realtime for that `item_id` (if recent) or surface it as "still processing" / offer manual retry. **This design specifies the mechanism (store-level staleness check, mirroring SS-010's `wardrobe.store.ts` "stale" pattern already documented there) but the exact resume screen/UX is Architect's own reasonable choice, not ticket-pinned** — flagged in Open questions as needing a product nod on whether resume happens automatically or via a dismissible banner.
- Batch with one failure: `useWardrobeBatchStore` marks that item `'failed'` and calls `advanceToNext()` regardless — the batch loop never blocks on one failure. `BatchSummaryToast` tallies `saved` vs `failed` counts at the end.
- Very slow network (2G): `SLOW_NETWORK_HINT_DELAY_MS = 10000` timer in `ProcessingStep`, shows "This may take longer on slow connections" — timer resets per stage transition (upload → bg-removal → tagging), not a single global 10s window, since each stage can independently be slow.
- Cancel at any step: `upload.tsx`'s header always renders a "Cancel"/back `IconButton`; pressing it calls `useWardrobeBatchStore.reset()` and `router.back()`. **New edge case:** cancelling mid-Processing does **not** cancel the already-dispatched server-side background tasks (SS-011/012 have no cancellation endpoint) — the `wardrobe_items` row will still complete processing server-side even though the user navigated away; the row simply won't be shown to the user until they revisit it (e.g. via SS-014's grid, once that exists). Flagged, not fixed — no cancellation API exists to call.
- **New edge case: `POST /wardrobe/tag` returns `404`** (per SS-012's design — this happens if `remove-bg` somehow didn't create the row, e.g. a bug or a race). Given this design always calls `remove-bg` before `tag` and awaits its `202` first, this should not occur in the normal path; if it does, `useProcessWardrobeItem` surfaces it as a processing failure (retry re-attempts from `remove-bg`, not just `tag`, since a `404` on `tag` implies the row genuinely doesn't exist).
- **New edge case: tagging completes with `status='flagged'`** (low confidence, moderation flag, or `containsPerson`) rather than `'tagged'`. Per the readiness signal above, `'flagged'` still counts as "ready to review" (the item isn't stuck) — Review renders the appropriate banner rather than blocking indefinitely on a status that will never become `'tagged'` for e.g. a permanently-low-confidence photo.
- **New edge case: signed-GET read path for `clean.png`/`original.jpg` doesn't exist yet** (`BL-046`, still open per SS-011/SS-012's own design docs). This ticket cannot render either image without *some* resolution mechanism. See Open questions — this is a real same-ticket blocker, not deferred silently.
- **New edge case: category dropdown search matching `wedding_guest` colour-key mismatch** — see Concrete values above, resolved via an explicit map, not left as a silent lookup miss (which would otherwise render every wedding-guest chip with an undefined colour).
- Never suggest white for `wedding_guest` (CLAUDE.md India rule) — not applicable here (this screen tags/reviews existing items, it doesn't suggest outfits); noted so a reviewer doesn't expect it in this ticket's scope.

## Test plan

**`mobile/__tests__/features/wardrobe/components/CaptureStep.test.tsx`:**
1. Renders the camera view with rear-facing default; tapping the flip `IconButton` toggles to front-facing.
2. Tapping "Gallery" invokes `launchImageLibraryAsync` with `selectionLimit: 10`, `allowsMultipleSelection: true`.
3. Selecting >10 images (mocked picker result) is clamped/rejected with a user-facing message, not silently truncated without explanation.
4. Renders the "photograph one item at a time" tip banner (`BL-057` copy) unconditionally on this step.
5. Camera permission denied, `canAskAgain=false` → renders "Open Settings" button; pressing it calls `Linking.openSettings()`.
6. Camera permission denied, `canAskAgain=true` → renders a re-request prompt, not the Settings button.

**`mobile/__tests__/features/wardrobe/components/ProcessingStep.test.tsx`:**
1. Renders "Removing background..." when `status='removing_bg'`, "Analysing your item..." when `status='tagging'`.
2. Batch mode renders `"{n}/{total}"` progress text matching `currentIndex`/`items.length`.
3. After `SLOW_NETWORK_HINT_DELAY_MS` elapses (fake timers) without a status change, renders the slow-network hint; hint does not appear before the delay.
4. `status='failed'` renders a retry button and a "skip, tag manually" option.

**`mobile/__tests__/features/wardrobe/components/ReviewStep.test.tsx`:**
1. Renders the BG-removed image when `processing_status='bg_removed'`; renders `original.jpg` with a fallback note when it's `'bg_pending'`.
2. Renders every `GarmentTagsDraft` field as an editable `Badge`/`Input`; toggling an occasion `Badge` updates local draft state (not yet saved).
3. `confidence < 0.7` renders the low-confidence banner; `confidence >= 0.7` does not.
4. `contentFlag='not_clothing'` renders "Doesn't look like clothing"; `contentFlag='nsfw'`/`'other'` renders the generic couldn't-process message, never the raw flag value.
5. `containsPerson=true` renders the flat-lay nudge without nulling/hiding a valid `category`.
6. `alternatives` present → renders a picker row; selecting an alternative swaps the primary `category` in the draft.
7. Pressing "Looks Good!" calls `useSaveWardrobeItemTags` with the current (possibly-edited) draft, then advances the batch (`advanceToNext`) or shows `BatchSummaryToast` on the last item.

**`mobile/__tests__/features/wardrobe/components/CategoryPicker.test.tsx`:**
1. Opens via `present()`, lists all 21 categories.
2. Typing a filter string narrows the visible rows (substring match, case-insensitive).
3. Selecting a row calls `onSelect` with the exact category value and dismisses the sheet.

**`mobile/__tests__/features/wardrobe/components/BatchSummaryToast.test.tsx`:**
1. Renders correct success/failure counts from a mixed batch.
2. "Add another" calls `reset()` and navigates back to Capture.
3. "View wardrobe" navigates to `/(tabs)/wardrobe`.

**`mobile/__tests__/features/wardrobe/wardrobe.store.test.ts`** (additions):
1. `initBatch` seeds `items` from the given sources, `currentIndex=0`.
2. `updateItemStatus`/`updateItemTags` mutate only the targeted item.
3. `advanceToNext` increments `currentIndex` and is a no-op past the last item (batch-summary is a separate signal, not an out-of-bounds index).
4. `reset` clears `items` back to empty and `currentIndex` to 0.

**`mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx`** (additions):
1. `useProcessWardrobeItem` calls `removeBackground` then `tagItem`, in that order (`await`s the first before firing the second).
2. If `removeBackground` rejects, `tagItem` is never called.
3. `useSaveWardrobeItemTags` issues a scoped `.update()` against `wardrobe_items` for the given `itemId` with exactly the edited fields.

**`mobile/__tests__/features/wardrobe/wardrobe.service.test.ts`** (additions):
1. `removeBackground` POSTs to `/wardrobe/remove-bg` with `{item_id}` and the caller's bearer token, expects `202`.
2. `tagItem` POSTs to `/wardrobe/tag` with the same shape.
3. `subscribeToItemUpdates` subscribes with filter `id=eq.{itemId}` on the `wardrobe_items` table and invokes the callback on a mocked `UPDATE` payload; the returned unsubscribe function actually removes the channel.

**`mobile/__tests__/app/wardrobe/upload.test.tsx`:**
1. Starts on Capture; after a mocked single-item capture, transitions to Processing, then (on a mocked Realtime "ready" event) to Review.
2. Cancel button at each of the 3 steps calls `reset()` and navigates back.
3. Batch of 3 (2 succeed, 1 fails) ends on `BatchSummaryToast` with counts 2/1.

**`mobile/__tests__/app/(tabs)/wardrobe.test.tsx`** (modify): asserts the empty-state CTA's `onPress` calls `router.push('/wardrobe/upload')`.

**Not automatable this pass (manual/device verification):**
- Real camera capture + real gallery multi-select on a physical device (compounds `BL-013`, no device/LAN access in this pipeline).
- End-to-end timing against the AC's "processing completes within 15 seconds for a single item on 4G" — depends on real Replicate/Gemini latency, already renegotiated upward by `BL-058`/`BL-067` (BG-removal typical 4-8s / worst ~15s, tagging typical 4-7s / worst ~10s) — **combined, a worst-case single item could take up to ~25s sequentially, exceeding this ticket's own "within 15 seconds" AC.** Flagged as a real tension, not silently resolved — see Open questions.
- BottomSheet Android device-matrix behaviour for `CategoryPicker` (compounds `BL-010`).

## Open questions / blockers — RESOLVED (user decision, 2026-07-25)

1. **`BL-046` (read path) — DECIDED: option (b).** Developer is explicitly authorized to add one small backend endpoint, `GET /wardrobe/items/{id}/image-url`, returning a fresh short-lived presigned GET for `clean.png`/`original.jpg` as part of SS-013's own scope. This is a deliberate, authorized deviation from "no backend changes" stated above — not a scope violation. JWT-auth this endpoint the same way SS-011/SS-012's routers do (`get_current_user_id`), and verify the requesting user owns the item.
2. **Processing latency AC — DECIDED: renegotiate now.** The raw ticket's AC ("Processing completes within 15 seconds for a single item on 4G") is superseded by: **"typical case under 15 seconds; worst case up to ~25 seconds on a cold Replicate+Gemini start (sequential BG-removal + tagging), per `BL-058`/`BL-067`'s own renegotiated per-call worst-cases."** `docs/tickets/raw/SS-013.md`'s AC line should be read with this amendment; QA should verify against the amended figure, not the original 15s figure.

Both decisions made directly by the user (not deferred to Developer/QA) — see `docs/worklog/SS-013.md` Architect entry addendum.
3. **App-close/resume UX during processing is a mechanism-only design** (store exposes staleness, exact resume screen/banner UX not pinned) — needs a product nod on whether this auto-resumes or requires user action, deferred to Developer's reasonable judgement if not resolved before then.
4. **`BL-008` (occasion colour coverage gap) still applies** — 8 of 12 `occasion_type` values render neutral `Badge` chips in Review, same accepted pattern as SS-004/SS-005. Not re-opened, just re-scanned and reaffirmed (tag `tokens`).
5. **No per-user tagging cost cap (`BL-062`) and no read-path decision (`BL-046`) mean this ticket is the first UI surface that could make both of those gaps visible in practice** (a user hammering "Add another" repeatedly has no client-side throttle beyond the sequential single-flight batch loop) — not a new row, just noting the two existing Active rows now have a real UI consumer.

## Backlog deltas

Moved to **Resolved** in `docs/BACKLOG.md`:
- `BL-057` (ai) — resolved by this ticket's `CaptureStep` shipping the "photograph one item at a time" tip banner as permanent, unconditional UI copy on the Capture step, per the recorded 2026-07-25 decision.
- `BL-031` (infra) — **partially resolved.** This ticket closes the "Wardrobe tab CTA has a real destination" half (`wardrobe.tsx`'s empty-state CTA now routes to `/wardrobe/upload`). The other half (Home screen's nudge hiding once a user has ≥1 real item) is still open and remains owned by SS-014 — moved to **Resolved** only if `docs/BACKLOG.md`'s workflow permits a partial-resolution note; otherwise (per that file's own "Closing" convention expecting a clean full resolution) this row is instead **left Active with an appended clarifying note** rather than force-closed, since half the row's scope genuinely isn't done yet. **Decision made here: append the clarifying note, do not move to Resolved** — moving it now would incorrectly claim the Home-nudge half is also done.

Added to **Active**:
- No new row needed for the read-path gap — `BL-046` already covers it exactly; this design adds a clarifying note to `BL-046` (see below) rather than opening a duplicate.

Clarifying notes appended (not resolved, not moved) to existing Active rows scanned this pass (tags `infra`/`ai`/`tokens`):
- `BL-046` (infra, read path) — updated: the ticket that actually needs this first is **SS-013** (Review step's cutout preview), not SS-014 as the row's text previously assumed. Still fully open; this design explicitly declines to invent a resolution (see Open questions #1) and flags it as a likely same-ticket blocker for Developer.
- `BL-031` (infra, wardrobe CTA/nudge) — updated: SS-013 closes the Wardrobe-tab-CTA half. Stays Active until SS-014 closes the Home-nudge half.
- `BL-008` (tokens, occasion colour gap) — reaffirmed, not resolved; this ticket's Review chips are the latest consumer hitting the same 8-of-12 gap.
- `BL-058`/`BL-067` (ai, latency renegotiations) — reaffirmed; their combined effect on this ticket's own "<15s" AC is newly noted (see Open questions #2), not a new row.

## Risk: med

Justification: this is UI/frontend composition only — no new backend route is authored by default (Open question #1's possible small `image-url` endpoint is flagged, not committed, and would itself be a small, non-auth, non-payment, non-schema addition if it happens), no DB schema/migration, no RLS change, no secrets, no payments. It does touch camera/media-library permissions and a Supabase Realtime subscription, which carry some device/runtime-behavior risk, but neither is a one-way door per `OPERATOR_RULEBOOK.md` §C2 — a permission-flow bug or a Realtime wiring bug is fully recoverable via a follow-up fix, not irreversible or externally binding. Classified `med` rather than `low` specifically because of Open question #1 (a real, not-yet-authorized backend read-path decision this ticket's own scope surfaces) and #2 (a real AC-vs-measured-latency tension) — both need a human answer before Developer can fully proceed, which is more friction than a pure `low`-risk placeholder/copy ticket, but neither rises to `high`'s auth/payments/schema/secrets/external-facing bar. Fast lane (architect→developer→qa auto-chain), consolidated human review at the PR — but the two Open Questions above should be explicitly answered before/at Developer kickoff, not silently assumed.
