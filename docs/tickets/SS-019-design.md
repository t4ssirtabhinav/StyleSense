# SS-019 — Design: Fix SS-013 upload-flow regressions found in manual verification

## Scope restatement

The merged SS-013 upload flow (`mobile/app/wardrobe/upload.tsx` + its `features/wardrobe`
components) shipped with automated tests all green but several real-device/browser defects the
suite couldn't see. The headline defect: Gemini's auto-tagging output (SS-012, correctly computed
and stored server-side) never reaches the client's review form, because the Realtime row type and
handler only read 3 of the ~10 columns that matter, and the store action that would carry the rest
(`updateItemTags`) is wired but never called. This ticket widens the type, wires the handler, and
adds an integration-level test asserting the Realtime-row → store → ReviewStep prefill path
end-to-end — the specific gap that let this ship. It also fixes a handful of layout/UX defects
from the same manual pass (no-scroll review form, vertically-stacked chips, review-image spacing,
CaptureStep centering/feedback, post-save summary visibility) and — newly found during this design
pass, not previously root-caused — two additional gaps: tagging-`failed` currently has **no**
handler at all (the user is stuck on Processing forever), and the batch loop's catch-all treats a
`wardrobe_limit_reached` 403 identically to every other failure, retrying/failing every remaining
queued item one-by-one with a generic message instead of detecting it once and stopping cleanly.
Mark Worn/wear-history rework (SS-015, per `BL-071`) stays explicitly out of scope.

## Files to create/modify

- `mobile/features/wardrobe/wardrobe.types.ts` — widen `WardrobeItemRealtimeRow` to carry the tag
  columns and the `ai_tags.tagging` sub-fields the Review form needs; export `isWardrobeUploadError`
  from here instead of leaving it private to `wardrobe.queries.ts` (see below).
- `mobile/features/wardrobe/wardrobe.service.ts` — add `mapRealtimeRowToTagsDraft(row)`, a pure
  function co-located with `subscribeToItemUpdates` (the thing whose payload it decodes).
- `mobile/features/wardrobe/wardrobe.queries.ts` — replace the local `isWardrobeUploadError` with
  the one now exported from `wardrobe.types.ts` (no behavior change, single source of truth so
  `upload.tsx` can reuse the same guard for the `wardrobe_limit_reached` batch-stop fix).
- `mobile/app/wardrobe/upload.tsx` — wire the Realtime handler to `updateItemTags`; add a `failed`
  tagging-status branch; wrap the non-capture steps in a `ScrollView`; detect
  `wardrobe_limit_reached` in `processItem`'s catch block and stop the batch instead of looping.
- `mobile/features/wardrobe/components/ReviewStep.tsx` — wrap occasion/season `Badge` lists in
  `flex-row flex-wrap` containers; give the review image a distinct frame with spacing below it.
- `mobile/features/wardrobe/components/CaptureStep.tsx` — center the permission-request/denied
  placeholder text both axes; add a local capturing/loading indicator for `handleCapture`.
- `mobile/features/wardrobe/components/BatchSummaryToast.tsx` — accept an optional
  `limitReachedMessage` prop to surface the free-tier-cap explanation when that's why the batch
  stopped early.
- `mobile/features/wardrobe/components/ItemCard.tsx` — **no change expected.** SS-014's fix pass
  (PR #26, already merged) restructured the favourite `IconButton` to be a sibling, not a
  descendant, of the card's own `Pressable` — read the current file and confirmed the nested-
  `<button>` defect this ticket's root-cause #2 describes is already fixed. Grep confirmed no other
  `features/wardrobe/*` component nests a `Pressable`/button-role element inside another one. This
  AC item needs no code change, only a verification pass (see Test plan).
- `mobile/__tests__/app/wardrobe/upload.test.tsx` — the integration test home (already has the
  Realtime-driven review-step-transition scaffolding this ticket's prefill test extends).
- `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` — unit tests for
  `mapRealtimeRowToTagsDraft`.
- `mobile/__tests__/features/wardrobe/components/ReviewStep.test.tsx`,
  `.../CaptureStep.test.tsx`, `.../BatchSummaryToast.test.tsx` — extend existing suites (files
  exist per SS-013; confirm exact paths at Developer time) for the layout/UX ACs.

## Concrete values to use, not invent

**`WardrobeItemRealtimeRow` (widened) — column names transcribed verbatim from
`supabase/migrations/001_initial.sql` and `backend/services/wardrobe_tagging_service.py`'s
`tag_columns`/`_tagging_payload`, not re-derived:**

```ts
export interface WardrobeItemRealtimeRow {
  id: string;
  processing_status: WardrobeItemProcessingStatus;
  category: WardrobeCategory | null;
  subcategory: string | null;
  color_primary: string | null;
  color_secondary: string | null;
  pattern: string | null;
  fabric: string | null;
  occasion_tags: OccasionType[] | null;
  season_tags: SeasonTag[] | null;
  ai_tags: {
    tagging?: {
      status?: 'tagging' | 'tagged' | 'flagged' | 'failed';
      confidence?: number;
      alternatives?: WardrobeCategory[];
      moderation?: {
        content_flag?: WardrobeContentFlag;
        contains_person?: boolean;
      };
    };
    bg_removal?: { status?: string };
  } | null;
}
```

Note the backend never writes `tag_columns` at all on a `failed` result (`_mark_failed` passes
`tag_columns=None`) — so on `failed`, every one of `category`/`subcategory`/... will be whatever
they already were (`null` from `upsert_uploaded_row`'s initial insert). The client must not assume
these are populated just because the row shape declares them; the `failed` branch below
deliberately does not call `mapRealtimeRowToTagsDraft` for this reason.

**`mapRealtimeRowToTagsDraft` (`wardrobe.service.ts`):**

```ts
export function mapRealtimeRowToTagsDraft(
  row: WardrobeItemRealtimeRow,
): GarmentTagsDraft {
  const tagging = row.ai_tags?.tagging;
  return {
    category: row.category,
    subcategory: row.subcategory,
    colorPrimary: row.color_primary,
    colorSecondary: row.color_secondary,
    pattern: row.pattern,
    fabric: row.fabric,
    occasionTags: row.occasion_tags ?? [],
    seasonTags: row.season_tags ?? [],
    confidence: tagging?.confidence ?? 1,
    alternatives: tagging?.alternatives,
    contentFlag: tagging?.moderation?.content_flag ?? 'ok',
    containsPerson: tagging?.moderation?.contains_person ?? false,
  };
}
```

**`upload.tsx`'s Realtime handler — full replacement:**

```ts
unsubscribeRef.current = subscribeToItemUpdates(
  uploadResult.itemId,
  (row: WardrobeItemRealtimeRow) => {
    const taggingStatus = row.ai_tags?.tagging?.status;
    if (row.processing_status === 'bg_removed' && taggingStatus === 'tagging') {
      updateItemStatus(taskId, 'tagging', { itemId: uploadResult.itemId });
    }
    if (
      row.processing_status === 'bg_removed' &&
      (taggingStatus === 'tagged' || taggingStatus === 'flagged')
    ) {
      updateItemTags(taskId, mapRealtimeRowToTagsDraft(row));
      updateItemStatus(taskId, 'review', { itemId: uploadResult.itemId });
      setScreenStep('review');
    }
    // Newly found during this design pass (not in the ticket's own root
    // causes): a 'failed' tagging status previously had NO handler at all --
    // the user was stuck on Processing indefinitely. Falls back to the blank
    // draft (upload.tsx's existing `currentItem.tags ?? DEFAULT_TAGS_DRAFT`)
    // by deliberately NOT calling updateItemTags here, per the note above
    // about tag_columns being unpopulated on failure.
    if (row.processing_status === 'bg_removed' && taggingStatus === 'failed') {
      updateItemStatus(taskId, 'review', { itemId: uploadResult.itemId });
      setScreenStep('review');
    }
  },
);
```

`updateItemTags` must be pulled into the component via
`useWardrobeBatchStore((state) => state.updateItemTags)`, same pattern as the store's other
already-selected actions.

**`processItem`'s catch block — `wardrobe_limit_reached` batch-stop:**

```ts
} catch (rawError) {
  const uploadError = isWardrobeUploadError(rawError) ? rawError : null;
  if (uploadError?.code === 'wardrobe_limit_reached') {
    const store = useWardrobeBatchStore.getState();
    updateItemStatus(taskId, 'failed', { error: uploadError.message });
    for (const item of store.items) {
      if (item.status === 'queued') {
        updateItemStatus(item.taskId, 'failed', { error: uploadError.message });
      }
    }
    setLimitReachedMessage(uploadError.message);
    setScreenStep('summary');
    return;
  }
  updateItemStatus(taskId, 'failed', { error: 'Processing failed' });
  advanceToNext();
  const store = useWardrobeBatchStore.getState();
  const nextItem = store.items[store.currentIndex];
  if (nextItem && nextItem.status === 'queued') {
    void processItem(nextItem.taskId, nextItem.localUri);
  } else if (!nextItem) {
    setScreenStep('summary');
  }
}
```

`setLimitReachedMessage` is a new local `useState<string | null>` in `WardrobeUploadScreen`,
reset to `null` in `handleAddAnother`/`handleCancel`, passed to
`<BatchSummaryToast limitReachedMessage={limitReachedMessage} ... />`. This only fires on the
**upload** step's error (before an `itemId` exists) — `wardrobe_limit_reached` is a 403 from
`get-upload-url`'s free-tier-cap check (`WARDROBE_LIMIT_MESSAGE`, `wardrobe.constants.ts`), which
can only happen at `uploadMutation.mutateAsync`, never at `processMutation.mutateAsync` (bg-removal
has no cap check).

**`ScrollView` wrapping** — scope it to the non-`capture` steps only; the Capture step's
`CameraView` needs `flex: 1` full-bleed layout, not a scrolling ancestor:

```tsx
{screenStep === 'capture' ? (
  <CaptureStep onImagesSelected={handleImagesSelected} />
) : null}

{screenStep !== 'capture' ? (
  <ScrollView testID="upload-scroll-view" className="flex-1">
    {/* ProcessingStep / ReviewStep+CategoryPicker / BatchSummaryToast, unchanged */}
  </ScrollView>
) : null}
```

Follows the one existing precedent for this exact pattern in this codebase
(`mobile/app/edit-preferences.tsx`: `import { ScrollView, View } from 'react-native'`, plain
`<ScrollView className="flex-1">`, no `KeyboardAvoidingView`) rather than inventing a new one.
**Flag, not verified this session:** the ticket's own Technical Notes instruct checking
`https://docs.expo.dev/versions/v56.0.0/` before writing scroll/keyboard-handling code — this
Architect pass has no web-fetch tool available and could not do that live lookup. `[inference, not
verified]`: plain `ScrollView` is almost certainly still correct for the review form's text
`Input`s (this repo's own most recent precedent, `edit-preferences.tsx`, uses no
`KeyboardAvoidingView` either), but the Developer must actually open that URL before writing this
code, per the ticket's own instruction — don't skip it just because this design doc assumes the
precedent holds.

**Occasion/season chip wrapping (`ReviewStep.tsx`):**

```tsx
<View className="flex-row flex-wrap gap-xs">
  {OCCASION_TYPES.map((occasion) => ( <Badge ... /> ))}
</View>
<View className="flex-row flex-wrap gap-xs">
  {SEASON_TAGS.map((season) => ( <Badge ... /> ))}
</View>
```

`gap-xs` resolves via `tailwind.config.js`'s existing `spacing.xs = '4px'` token — no new token
needed. `Badge` has no `className` prop (by design, per its existing API) so inter-chip spacing
must come from the wrapping container's `gap`, not per-Badge margin.

**Review image frame (`ReviewStep.tsx`):** wrap the existing `<Image testID="review-image" ...>`
in a `<View className="mb-md overflow-hidden rounded-lg border border-textMuted">` — reuses the
exact border/radius token pair `Card`'s own `outlined` variant already uses
(`'rounded-sm border border-textMuted'`, bumped to `rounded-lg` to match the image's larger visual
weight), not an invented value.

**CaptureStep centering + capture-in-flight indicator:**

- Add `className="flex-1 items-center justify-center"` to both the `camera-permission-denied` and
  `camera-permission-request` `Card`s' containing area (or the `Card` itself — `Card`'s
  `className` prop is additive per its own doc comment, safe to add layout classes), and
  `text-center` on their `Text` children.
- Add `const [isCapturing, setIsCapturing] = useState(false)`, set `true` at the start of
  `handleCapture`, `false` in a `finally`. While `true`, render a `Skeleton` (reuse
  `components/ui`'s existing `Skeleton`, same component `ProcessingStep` already uses — no new
  spinner primitive needed) as an overlay over the `CameraView`, and disable the Capture `Button`
  (`disabled` prop — confirm `Button` supports one; if not, gate `onPress` with an
  `if (isCapturing) return;` guard instead).

## Edge cases

Carried forward from the raw ticket, plus new ones found while designing this fix:

- Tagging `status === 'failed'` — **no `tag_columns` are written server-side**, so the client must
  not call `mapRealtimeRowToTagsDraft` on this branch (would read back nulls that look like a
  real-but-empty prefill rather than an honest "AI failed, fill manually" state). Falls back to
  `DEFAULT_TAGS_DRAFT` by omission, not by an explicit empty-tags write.
- Tagging `status === 'flagged'` (low-confidence OR moderation) still prefills — `ReviewStep`'s
  existing `showLowConfidence`/`flagMessage` banners already read `draft.confidence`/
  `draft.contentFlag`, which now actually populate instead of always reading the `DEFAULT_TAGS_DRAFT`
  defaults (`confidence: 1`, `contentFlag: 'ok'`) that made those banners permanently unreachable
  in practice.
- A Realtime UPDATE can fire multiple times for the same terminal state (e.g. a duplicate `tagged`
  event) — `updateItemTags`/`updateItemStatus` are both idempotent overwrites keyed by `taskId`, so
  re-firing is harmless; no dedupe guard needed.
- `wardrobe_limit_reached` mid-batch: previously, every remaining queued item independently called
  `uploadMutation.mutateAsync`, each rejecting with the same 403, each producing a separate generic
  "Processing failed" — same failure, N confusing toasts/rows instead of one clear stop. Fixed by
  detecting the specific error code once and marking the rest of the queue failed without further
  network calls.
- `wardrobe_limit_reached` on the **very first** item of a batch (user already at/over the cap
  before this session) — same code path, `store.items` at that point has `currentIndex === 0` and
  the rest `queued`; still resolves correctly to "0 added, N failed" + the cap message, not a loop.
- CaptureStep's new `isCapturing` guard must not block the *Gallery* path — it's local state scoped
  to `handleCapture` only; `handleGalleryPress`'s own async gap is already handled by the OS's own
  native picker UI taking over the screen, per the existing design doc's original reasoning; no
  double-indicator needed there.
- ReviewStep's `ScrollView` wrapping must not double-nest with anything `ReviewStep`/
  `BatchSummaryToast` might independently add — neither currently uses its own `ScrollView`;
  confirm this stays true if either changes in a future ticket.

## Test plan

- `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts`
  - `mapRealtimeRowToTagsDraft` maps every one of the 8 tag columns plus `confidence`/
    `alternatives`/`contentFlag`/`containsPerson` correctly from a fully-populated row.
  - `mapRealtimeRowToTagsDraft` defaults `occasionTags`/`seasonTags` to `[]` and
    `confidence`/`contentFlag`/`containsPerson` to their `DEFAULT_TAGS_DRAFT`-equivalent values
    when `ai_tags.tagging` is absent (defensive — shouldn't happen given the calling site's own
    guard, but the function must not throw).
- `mobile/__tests__/app/wardrobe/upload.test.tsx` (**integration-level**, per the ticket's own
  Technical Notes — extends the existing Realtime-driven test scaffolding already in this file,
  does not mock `updateItemTags` itself):
  - New test: after a Realtime `onUpdate` fires with `processing_status: 'bg_removed'`,
    `ai_tags.tagging.status: 'tagged'`, and populated tag columns, `ReviewStep`'s rendered fields
    (category button label, subcategory/colour/pattern/fabric `Input` values, selected occasion/
    season `Badge`s) show the **Realtime row's values**, not the blank defaults — asserted via
    real rendered output (`getByText`/`Input`'s `value` prop via `getByDisplayValue` or similar),
    not by mocking `updateItemTags` and asserting a call (the ticket's Technical Notes flag that a
    call-was-made assertion alone is exactly the kind of shallow coverage that let this ship).
  - New test: a `flagged` status with `confidence: 0.4` still prefills the tag fields **and**
    shows `low-confidence-banner`.
  - New test: a `failed` status transitions to the Review step (not stuck on Processing) with all
    fields blank/default, and does not crash.
  - New test: a batch where the first item's upload rejects with
    `{ code: 'wardrobe_limit_reached', message: WARDROBE_LIMIT_MESSAGE, retryable: false }` ends
    on `batch-summary-toast` with every item marked failed and the limit message visible, without
    a separate `uploadMutation.mutateAsync` call per remaining queued item (assert
    `mockUploadMutateAsync` was called exactly once, not N times).
- `mobile/__tests__/features/wardrobe/components/ReviewStep.test.tsx`
  - Occasion badges' wrapping container has `flex-row flex-wrap` classes (or: renders all 12 +
    4 badges without asserting layout directly, since RNTL/jsdom can't measure actual wrapped
    rows — assert the className contract, not pixel layout).
  - `review-image`'s wrapping `View` carries the new frame classes.
- `mobile/__tests__/features/wardrobe/components/CaptureStep.test.tsx`
  - Permission-denied/request Cards render with centering classes present.
  - Pressing Capture sets a visible loading state (`Skeleton`/disabled Capture button) until
    `takePictureAsync` resolves; a second press while capturing does not call
    `takePictureAsync` twice.
- `mobile/__tests__/features/wardrobe/components/BatchSummaryToast.test.tsx`
  - Renders `limitReachedMessage` text when the prop is present; renders nothing extra when
    absent (existing counts-only behavior unchanged).
- `mobile/__tests__/features/wardrobe/components/ItemCard.test.tsx` — no new test required; existing
  suite (from SS-014's fix pass) already covers the sibling-not-descendant structure. Developer
  should re-run it as a regression check, not extend it.
- Full existing SS-013 suite (`upload.test.tsx`'s 5 pre-existing tests,
  `ReviewStep`/`CaptureStep`/`ProcessingStep`/`BatchSummaryToast` suites) must still pass unchanged
  — none of the above renames/removes an existing testID or prop the old tests depend on.

## Open questions / blockers

- **Expo v56 scroll/keyboard docs not actually checked this session** (no web-fetch tool available
  to this Architect pass) — flagged above under "ScrollView wrapping". Developer must check
  `https://docs.expo.dev/versions/v56.0.0/` before implementing, per the ticket's own instruction;
  this design's plain-`ScrollView` choice is `[inference from existing repo precedent, not
  verified against current Expo docs]`.
- **AC "post-save screen shows a real summary state" — root cause not independently confirmed.**
  `BatchSummaryToast` already exists, is already wired at `screenStep === 'summary'`, and an
  existing passing test (`upload.test.tsx`'s 3-item-batch test) already asserts it renders with
  correct counts. The most plausible explanation for the manually-observed "blank screen with only
  a close affordance" is the same missing-`ScrollView`/container root cause as the no-scroll AC —
  the summary `Card` rendering below the fold with only the always-visible top `IconButton` close
  button in the initial viewport — which this design's `ScrollView` wrapping (now covering the
  `summary` step too) should incidentally fix. This is `[inference]`, not independently
  root-caused the way items 1-4 were; **flagging for QA to specifically re-verify this AC** after
  the `ScrollView` change lands, rather than assuming it's resolved as a side effect.
- **Two orchestrator-identified candidate-scope items, resolved as follows (not silently
  folded in or dropped):**
  1. `computeBatchDedupeHash` (fully built, unit-tested, zero production callers) — **deferred**,
     not folded into this ticket. Wiring it needs extracting base64 from the already-compressed
     image (a new step in `compressImageForUpload`'s call chain), computing+comparing hashes
     across the in-flight batch in `handleImagesSelected`, and deciding the UX for a detected
     duplicate (skip silently? prompt?) — meaningfully more design surface than this ticket's
     "fix what manual verification found" framing, and not something manual verification actually
     flagged. Logged as `BL-072` (Active).
  2. `processItem`'s catch-block treating every failure identically, including
     `wardrobe_limit_reached` — **folded into this ticket's scope** (see "Concrete values" above
     and the ticket's own AC list amendment below). Contained to the same catch block already
     being touched for the headline fix, low implementation risk, and a real user-facing
     confusion bug (N identical-looking generic failures instead of one clear stop) — worth fixing
     in the same pass rather than deferring.
- **Raw ticket AC list amendment**: add explicit ACs for (a) tagging-`failed` transitioning to
  Review with blank defaults rather than hanging on Processing forever (found during this design
  pass, not in the ticket's own root-cause list), and (b) `wardrobe_limit_reached` stopping the
  batch once with a clear message rather than repeating per remaining item (candidate item #2
  above, folded in). Both are additive to the existing AC list, not replacements — no existing AC
  is weakened.

## Backlog deltas

- **Added `BL-072`** (Active, tag `infra`): `computeBatchDedupeHash` unwired — deferred out of this
  ticket's scope, see Open questions above.
- **No existing Active row resolved by this ticket** — scanned `docs/BACKLOG.md`'s Active table by
  tag (`ai`/`infra`/`test`, the tags plausibly relevant to a wardrobe-upload-flow bug-fix ticket);
  none of `BL-062` (tagging cost cap), `BL-058`/`BL-067` (latency ACs), `BL-064` (pattern/fabric
  vocabulary), or `BL-071` (Mark Worn wear-history rework) are resolved or touched by this ticket's
  scope. Left open, not silently re-deferred.

## Risk classification

`Risk: med` — confirmed, no revision from the ticket header's own classification. This ticket
touches only client-side wiring (types, a Realtime handler, layout/UX) plus one client-side error-
branching fix in an already-shipped, non-auth, non-payment, non-schema, non-RLS upload flow. No
migration, no new endpoint, no secrets, nothing externally-facing beyond what SS-013 already
shipped. Fast lane is appropriate.
