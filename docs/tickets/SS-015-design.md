# SS-015 — Wardrobe Item Edit, Delete & Mark Worn — Design

## Scope restatement

This ticket completes CRUD on a wardrobe item from SS-014's `ItemDetailSheet`. Three parts, of which one is materially larger than the raw ticket describes:

1. **Edit** — SS-014 already ships `EditItemTagsForm` (category/subcategory/colours/pattern/fabric/occasion/season). SS-015 extends it with the fields the raw ticket names but SS-014 never built: `brand`, `purchase_price` (₹ Indian formatting), `purchase_date`, and `user_notes` (max 500 chars with a live character count). Saved through the same RLS-scoped `UPDATE` path.
2. **Delete** — keeps SS-014's two-step confirm, adds true optimistic removal from the grid, and **actually cleans up the item's R2 objects** (`original.jpg`/`clean.png`/`thumbnail.jpg`) via a new authenticated backend endpoint that deletes the DB row and then fires an async storage cleanup. This resolves `BL-068`.
3. **Mark Worn — rebuilt per `BL-071`, not as the raw ticket describes it.** The user tested SS-014's single-tap `wear_count + 1` / `last_worn_at = today` control and rejected it: it can only ever say "today", inflates without bound on repeated taps, and a mis-tap is uncorrectable. The product decision (2026-07-27) is a **full dated wear-history log**: a new `wardrobe_item_wears` table, one row per wear, each viewable/editable/deletable, with `wear_count` and `last_worn_at` becoming **trigger-maintained derived caches** on `wardrobe_items` rather than columns any client writes. `cost_per_wear` stays exactly as it is — a `GENERATED ALWAYS ... STORED` column off `wear_count` — and keeps working unchanged precisely *because* the derivation is implemented as a trigger that writes `wear_count` (which re-evaluates the stored generated column) rather than as a view that would have required dropping and recreating it.

That third part means this ticket carries a **new table, a new migration, a new RLS policy, a trigger, and a one-way backfill of existing wear data** — schema surface the raw ticket's own "Status note" explicitly (and now incorrectly) says does not exist. That note is superseded by `BL-071`; see Open questions #1.

The raw ticket's outfit-cascade edge cases ("item in a saved outfit", "outfit marks the item removed, suggests a replacement") stay deferred — `outfits`/`suggestion_sessions` exist in `001_initial.sql` but no code anywhere writes to them yet, so building cascade logic now would be dead code against a table with no writer. Explicitly out of scope, per the ticket's own Status note.

## Files to create/modify

### Database (`supabase/migrations/`) — the load-bearing part of this ticket

- `supabase/migrations/006_wardrobe_item_wears.sql` — **new**. Full contents specified verbatim under "Concrete values to use, not invent" below. Applied via `supabase db push` (the established path since SS-011; note `BL-003` — one shared project backs both `develop` and `main`, so applying this migration affects the only live database there is).
- `mobile/types/supabase.ts` — **regenerate, never hand-edit**, after the migration is applied:
  `supabase gen types typescript --project-id mefpfykuinasgkpfhmzk --schema public > mobile/types/supabase.ts`
  (exact command per `docs/tickets/SS-002-design.md`'s precedent, reused by SS-011.) The new `wardrobe_item_wears` table must appear in the generated `Tables` union before any frontend code referencing it will type-check.

### Backend (`backend/`) — delete + R2 cleanup only (no wear-history backend surface; wears are a direct RLS-scoped Supabase table like SS-014's other item writes)

- `backend/routers/wardrobe.py` — **modify**. Add `DELETE /wardrobe/items/{item_id}`. JWT-authed via the existing `get_current_user_id` + `_extract_bearer_token` pair; validates `item_id` is a UUID (422 otherwise, same `uuid.UUID(...)` guard as `get_item_image_url`); calls `repository.get_item_image_info(jwt=..., item_id=...)` to capture the R2 keys **before** deleting; 404 if `None` (covers both "doesn't exist" and "not owned" — same not-an-ownership-oracle posture as the two existing item endpoints); calls `repository.delete_item(...)`; then `background_tasks.add_task(deletion_service.cleanup_storage, ...)`. Returns `200 {"status": "deleted", "item_id": "..."}`. Order is **DB row first, storage second** — the reverse would risk an item that survives with its images gone.
- `backend/adapters/interfaces.py` — **modify**. Add `IWardrobeRepository.delete_item(self, *, jwt: str, item_id: str) -> bool` (RLS-scoped `.delete().eq("id", item_id)`; returns whether a row was removed).
- `backend/adapters/wardrobe_repository.py` — **modify**. Implement the above, same RLS-scoped-client construction the file already uses for every other method (never `service_role`).
- `backend/adapters/r2_storage.py` — **modify**. Add `delete_objects(self, keys: list[str]) -> None` wrapping boto3's batch `delete_objects(Bucket=..., Delete={"Objects": [{"Key": k}, ...]})`. Synchronous like every other method on this class; the caller offloads via `asyncio.to_thread` (the class docstring already states this contract). Note the module docstring already records that `delete_object` was live-verified against the real `stylesense-media` bucket during SS-011.
- `backend/services/wardrobe_deletion_service.py` — **new**. Single-responsibility service (per CLAUDE.md's `services/` convention): `cleanup_storage(*, user_id, item_id, keys)` → `await asyncio.to_thread(self._storage.delete_objects, keys)`, wrapped in try/except that `logger.exception`s and swallows (a failed cleanup must never surface as an error to a user whose item is already gone). Keys are derived from the row read before deletion, filtered to non-null values.
- `backend/tests/test_wardrobe_router.py` — **modify**. Delete-endpoint cases.
- `backend/tests/test_wardrobe_repository.py` — **modify**. `delete_item` cases.
- `backend/tests/test_wardrobe_deletion_service.py` — **new**.
- `backend/tests/test_r2_storage.py` — **modify**. `delete_objects` case.

### Frontend (`mobile/features/wardrobe/`)

- `mobile/features/wardrobe/wardrobe.types.ts` — **modify**. Add `export type WardrobeItemWearRow = Tables<'wardrobe_item_wears'>;` (generated types only — CLAUDE.md), `WardrobeItemDetailsDraft` (`brand`/`purchasePrice`/`purchaseDate`/`userNotes`), and `LogWearResult = { wearCount: number; costPerWear: number | null; wornOn: string }`.
- `mobile/features/wardrobe/wardrobe.constants.ts` — **modify**. Add `MAX_USER_NOTES_LENGTH = 500`, `WEAR_TOAST_DURATION_MS = 3000`, and the exact copy strings listed under "Concrete values".
- `mobile/features/wardrobe/wardrobe.service.ts` — **modify**.
  - **Remove `markWardrobeItemWorn`** entirely (the client-computed `wear_count + 1` write). It is replaced, not augmented — leaving it in place would let a client write a column the trigger now owns.
  - Add `fetchWardrobeItemWears(itemId)`, `logWardrobeItemWear(itemId, userId, wornOn)`, `updateWardrobeItemWear(wearId, wornOn)`, `deleteWardrobeItemWear(wearId)` (all direct RLS-scoped Supabase calls on `wardrobe_item_wears`, same shape as SS-014's favourite write).
  - Add `fetchWardrobeItemWearStats(itemId)` — `select('wear_count, cost_per_wear').eq('id', itemId).single()`, used to read back the trigger-recomputed values for the toast (never recomputed client-side; `cost_per_wear` is a generated column, see `BL-004`).
  - Add `saveWardrobeItemDetails(itemId, details)` — `UPDATE` of `brand`/`purchase_price`/`purchase_date`/`user_notes` only.
  - Replace `deleteWardrobeItem(itemId)`'s body with a `DELETE` fetch to `${EXPO_PUBLIC_BACKEND_URL}/wardrobe/items/${itemId}` carrying `Authorization: Bearer <jwt>` (signature gains a `jwt` param). No hardcoded URLs — `constants/api.ts` only.
- `mobile/features/wardrobe/wardrobe.queries.ts` — **modify**.
  - Delete `useMarkWardrobeItemWorn` / `MarkWardrobeItemWornInput`.
  - Add `wardrobeItemWearsQueryKey(itemId)`, `useWardrobeItemWearsQuery(itemId)`, `useLogWardrobeItemWear()` (returns `LogWearResult` for the toast; invalidates the wears key + the grid keys), `useUpdateWardrobeItemWear()`, `useDeleteWardrobeItemWear()`, `useSaveWardrobeItemDetails()`.
  - `useToggleWardrobeItemFavourite` — add real optimistic behaviour (`onMutate` patches the cached items array, `onError` rolls back to the snapshot, `onSettled` invalidates). SS-014 shipped invalidate-only, which is not what the AC's "instant" means.
  - `useDeleteWardrobeItem` — takes `jwt`; `onMutate` removes the item from the cached array (AC: "removes the item from the grid immediately"), `onError` restores it, `onSettled` invalidates.
  - Wire `ANALYTICS_EVENTS` only where an event already exists — do **not** invent new event names (see `BL-049`; no wear/edit/delete event is defined in `constants/analyticsEvents.ts`, so none is emitted here).
- `mobile/features/wardrobe/components/ItemDetailSheet.tsx` — **modify**. The "Mark Worn" `ActionTile` now (a) logs today's wear via `useLogWardrobeItemWear` and (b) shows the toast. The read-only stats block ("Worn N× / Last worn: …") becomes a pressable row opening the wear history. Delete passes `jwt`. The favourite tile keeps its current label/accessibility behaviour and gains the heart animation.
- `mobile/features/wardrobe/components/WearHistorySection.tsx` — **new**. Rendered inside `ItemDetailSheet` as a third `mode` (`'view' | 'edit' | 'wears'`, extending the existing local-state pattern — no new route, no nested bottom sheet, which `@gorhom/bottom-sheet` handles poorly and `BL-010` already flags as unverifiable on the Android matrix). Lists every wear row newest-first (date in `'en-IN'`/`Asia/Kolkata`), each with an edit control (opens `WearDateField` inline) and a delete control (two-step arm/confirm, same pattern as item delete), plus an "Add a wear" affordance for a past date. Loading/error/empty states all handled (CLAUDE.md).
- `mobile/features/wardrobe/components/WearDateField.tsx` — **new**. Date entry **without adding a native date-picker dependency** (none is installed; `@react-native-community/datetimepicker` is a new native module with weak web support, and this app is web-first): two quick-pick `Badge`s ("Today", "Yesterday") plus a `DD/MM/YYYY` `Input` validated locally. Rejects unparseable input, future dates, and (if `purchase_date` is set) dates before purchase. See Open question #4.
- `mobile/features/wardrobe/components/WearLoggedToast.tsx` — **new**, local to this domain. There is no `Toast` in `components/ui/` and this design does not add one (SS-014's established "no new `components/ui` primitives" precedent; a portal-based global toast interacting with an open bottom sheet is exactly the kind of thing `BL-010` says we cannot verify on device). An in-sheet `Card` banner that auto-dismisses after `WEAR_TOAST_DURATION_MS`, using `react-native-reanimated` (already installed) for fade-in/out.
- `mobile/features/wardrobe/components/EditItemTagsForm.tsx` — **modify**. Adds the detail fields below the existing tag fields: `brand` (`Input variant="text"`), `purchase_price` (numeric `Input`, displayed with `Intl.NumberFormat('en-IN')` grouping, stored as an integer), `purchase_date` (reuses `WearDateField`), `user_notes` (multiline `Input` with a live `{n}/500` counter and a hard `maxLength`). "Save" now calls `useSaveWardrobeItemTags` **and** `useSaveWardrobeItemDetails`; both must succeed before `onSaved` fires (see Edge cases for the partial-failure path).

### Tests

- `mobile/__tests__/features/wardrobe/components/WearHistorySection.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/WearDateField.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/WearLoggedToast.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/components/ItemDetailSheet.test.tsx` — **modify** (its existing "Mark Worn calls `useMarkWardrobeItemWorn` with `wear_count + 1`" case is deleted, not adapted — that hook no longer exists).
- `mobile/__tests__/features/wardrobe/components/EditItemTagsForm.test.tsx` — **modify**.
- `mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx` — **modify**.
- `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` — **modify**.
- Backend test files as listed above.

**Explicitly not touched:** `ItemCard.tsx` (still reads `wear_count` off the item row — unchanged shape, now trigger-maintained), `wardrobe.selectors.ts` (`most_worn`/`least_worn`/`cost_per_wear` sorts keep working off the same columns), the `outfits` table and anything Epic 3.

## Concrete values to use, not invent

### `supabase/migrations/006_wardrobe_item_wears.sql`

Transcribe this; do not restyle it. It follows `005_wardrobe_processing_status.sql`'s header-comment convention.

```sql
-- ============================================================
-- SS-015 — Dated wear history (resolves BL-071)
-- Replaces the single wear_count/last_worn_at scalar pair with an
-- append-only per-wear log. wear_count/last_worn_at become
-- trigger-maintained caches; cost_per_wear (GENERATED ALWAYS ... STORED
-- off wear_count, see BL-004) is unchanged and recomputes automatically
-- whenever the trigger writes wear_count.
-- Apply via: supabase db push (linked project).
-- ============================================================

-- Needed for the composite FK below (defence-in-depth: a wear row can
-- never point at an item belonging to a different user, independent of RLS).
ALTER TABLE wardrobe_items
  ADD CONSTRAINT wardrobe_items_id_user_id_key UNIQUE (id, user_id);

CREATE TABLE wardrobe_item_wears (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id    UUID NOT NULL,
  user_id    UUID NOT NULL,
  worn_on    DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT wardrobe_item_wears_item_fk
    FOREIGN KEY (item_id, user_id)
    REFERENCES wardrobe_items (id, user_id) ON DELETE CASCADE,
  -- At most one wear per item per day: makes the "Mark Worn" tap
  -- idempotent and stops repeat taps inflating the count (BL-071's
  -- primary complaint). See design doc Open question #2.
  CONSTRAINT wardrobe_item_wears_one_per_day UNIQUE (item_id, worn_on)
);

CREATE INDEX idx_item_wears_item_worn_on ON wardrobe_item_wears (item_id, worn_on DESC);
CREATE INDEX idx_item_wears_user_id      ON wardrobe_item_wears (user_id);

ALTER TABLE wardrobe_item_wears ENABLE ROW LEVEL SECURITY;

-- Same "fully private to owner" shape as user_owns_wardrobe, but with an
-- explicit WITH CHECK (writes are validated, not just reads).
CREATE POLICY "user_owns_item_wears" ON wardrobe_item_wears
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Recomputes the derived cache for one item from the log. SECURITY
-- INVOKER (the default) on purpose: the caller is always the row's owner,
-- so user_owns_wardrobe permits the UPDATE, and no policy is bypassed.
CREATE OR REPLACE FUNCTION sync_wardrobe_item_wear_stats(target_item_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE wardrobe_items w
  SET wear_count   = COALESCE(stats.wear_count, 0),
      last_worn_at = stats.last_worn_at
  FROM (
    SELECT COUNT(*)::INTEGER AS wear_count, MAX(worn_on) AS last_worn_at
    FROM wardrobe_item_wears
    WHERE item_id = target_item_id
  ) AS stats
  WHERE w.id = target_item_id;
END;
$$;

CREATE OR REPLACE FUNCTION trg_sync_wardrobe_item_wear_stats()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    PERFORM sync_wardrobe_item_wear_stats(OLD.item_id);
  END IF;
  IF TG_OP <> 'DELETE' AND (TG_OP = 'INSERT' OR NEW.item_id IS DISTINCT FROM OLD.item_id) THEN
    PERFORM sync_wardrobe_item_wear_stats(NEW.item_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE TRIGGER wardrobe_item_wears_sync_stats
AFTER INSERT OR UPDATE OR DELETE ON wardrobe_item_wears
FOR EACH ROW EXECUTE FUNCTION trg_sync_wardrobe_item_wear_stats();

-- Backfill: SS-014's scalar counter recorded only a total and a single
-- date, so the individual wears it counted are unrecoverable. Every item
-- with a last_worn_at gets exactly ONE wear row on that date; every other
-- item's counter is reset to 0. This is lossy by necessity and is
-- acceptable only because all existing wear data is pre-launch test taps
-- (see design doc Open question #3).
INSERT INTO wardrobe_item_wears (item_id, user_id, worn_on)
SELECT id, user_id, last_worn_at
FROM wardrobe_items
WHERE last_worn_at IS NOT NULL AND user_id IS NOT NULL
ON CONFLICT DO NOTHING;

UPDATE wardrobe_items w
SET wear_count   = COALESCE(stats.wear_count, 0),
    last_worn_at = stats.last_worn_at
FROM (
  SELECT i.id,
         (SELECT COUNT(*)::INTEGER FROM wardrobe_item_wears x WHERE x.item_id = i.id) AS wear_count,
         (SELECT MAX(worn_on)      FROM wardrobe_item_wears x WHERE x.item_id = i.id) AS last_worn_at
  FROM wardrobe_items i
) AS stats
WHERE w.id = stats.id;

COMMENT ON COLUMN wardrobe_items.wear_count IS
  'Derived cache maintained by wardrobe_item_wears'' trigger (SS-015). Never write directly.';
COMMENT ON COLUMN wardrobe_items.last_worn_at IS
  'Derived cache maintained by wardrobe_item_wears'' trigger (SS-015). Never write directly.';
```

**Why a trigger-maintained column and not a view:** `cost_per_wear` is `NUMERIC GENERATED ALWAYS AS (CASE WHEN wear_count > 0 THEN purchase_price::numeric / wear_count ELSE purchase_price END) STORED` (`001_initial.sql` lines 63-68). A generated column can only reference columns of its own row, so `wear_count` must remain a real column on `wardrobe_items`. Replacing it with a view or a subquery would require dropping and recreating `cost_per_wear` — a strictly more destructive migration with no benefit. Because the column is `STORED`, Postgres recomputes it on every `UPDATE` of the row, so the trigger's `SET wear_count = ...` is exactly what keeps `cost_per_wear` correct. `BL-004`'s gap (generated columns are typed optional, not banned, in the generated TS types) is unchanged and now applies to `wear_count`/`last_worn_at` too — mitigated here by removing the only client write path rather than by types.

### Copy and formatting

- Wear-logged toast (`purchase_price` present): `Outfit logged! Cost per wear: ₹X` — X via `Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })`, matching `ItemDetailSheet`'s existing `formatIndianCurrency` helper (reuse it, don't re-author).
- Wear-logged toast (`purchase_price` null → `cost_per_wear` null): `Wear logged for {date}` — never render `₹null`/`₹NaN`.
- Already-logged-today: `Already logged for today` (the `ON CONFLICT` no-op path).
- Notes counter: `{n}/500`, rendered as `Text variant="caption"`.
- Dates everywhere: `'en-IN'` locale, `Asia/Kolkata` timezone — reuse `ItemDetailSheet`'s existing `formatLastWornDate`.
- Delete confirm: unchanged from SS-014 (`Delete` → `Confirm delete`, two taps).

### R2 key layout (already fixed elsewhere — transcribe, don't invent)

`wardrobe/{user_id}/{item_id}/original.jpg`, `…/clean.png`, `…/thumbnail.jpg` (`backend/services/wardrobe_bg_removal_service.py` lines 47/51/55). The DB columns `image_url` / `image_clean_url` / `thumbnail_url` store **keys, not URLs** (confirmed by how `get_item_image_url` passes them straight into `generate_presigned_get_url`) — so the cleanup task deletes exactly those three column values where non-null, and does not reconstruct paths by string templating.

## Edge cases

Carried forward from the raw ticket:

- **Purchase price of 0 (gifted)** — valid. `cost_per_wear` evaluates to `0` (the `ELSE purchase_price` branch when `wear_count = 0`, or `0 / n` otherwise); the toast renders `₹0`, not a blank or an error.
- **Item in a saved outfit / deleting an item in an outfit** — deferred, per the ticket's own Status note: nothing writes to `outfits` yet. Not implemented, not stubbed.

New, from designing against the current codebase:

- **Repeat "Mark Worn" taps in one day** — collapse to a single row via the unique constraint + `ON CONFLICT DO NOTHING`; the UI reports "Already logged for today" rather than silently doing nothing or double-counting. This is the specific defect `BL-071` was raised over.
- **Deleting the last remaining wear row** — trigger sets `wear_count = 0` and `last_worn_at = NULL`; `cost_per_wear` falls back to `purchase_price`. The UI must render "Never worn", not "Worn 0× · Last worn: null".
- **Editing a wear onto a date that already has one** — hits the unique constraint (`23505`). Surface "A wear is already logged for that date", don't leak the Postgres error string.
- **Future-dated / pre-purchase wear** — rejected client-side by `WearDateField` before any write (no DB check constraint: `purchase_date` can change after the fact, which would retroactively invalidate stored rows).
- **Deleting an item with wear history** — `ON DELETE CASCADE` on the composite FK removes the wear rows. No orphan rows, no trigger fallout (the parent row is gone before the cascade's trigger firing would matter; the trigger's `UPDATE` simply matches zero rows).
- **Delete succeeds in the DB, R2 cleanup fails** — the user's item is gone (correct); the objects are orphaned exactly as they are today. Logged via `logger.exception`, never surfaced to the user, never retried. This is the residual of `BL-068`, logged as new `BL-074`.
- **Delete while offline / backend unreachable** — the delete now goes through FastAPI (not Supabase directly), so it fails where SS-014's direct-table delete would have succeeded. The optimistic removal must roll back and show an error. Note the backend has never been deployed (`BL-037`), so this endpoint — like `remove-bg`/`tag`/`image-url` before it — only works against a locally running `uvicorn`. Not a new constraint, but delete is the first *destructive* action to inherit it.
- **`user_notes` at exactly 500 chars** — allowed; 501 is not enterable (`maxLength`), and the counter renders `500/500` without an error state (there is still no error/danger colour token — `BL-007`).
- **`purchase_price` unit ambiguity** — `001_initial.sql` line 59 comments the column as "in paise", but SS-014's shipped `ItemDetailSheet` formats it directly as rupees, and this ticket's AC ("₹1,23,456 via `Intl.NumberFormat('en-IN')`") reads as whole rupees. These cannot both be right, and `cost_per_wear` inherits whichever unit is wrong. See Open question #5.
- **Concurrent edit of tags + details** — `EditItemTagsForm`'s Save fires two `UPDATE`s against the same row. They touch disjoint column sets, so neither clobbers the other, but the second can fail after the first succeeded, leaving a half-saved edit. The form keeps its draft and surfaces a retryable error rather than closing on partial success.
- **Account switch on the same device** — the wears query is keyed by `itemId` only (item ids are globally unique UUIDs and RLS scopes reads), unlike the grid's user-keyed keys. Safe, but noted so it isn't read as an inconsistency.

## Test plan

**`supabase` / DB behaviour** — no live-DB test harness exists in this repo (`backend/tests/test_db_schema.py` has never actually run, `BL-005`), so the trigger's behaviour is **not** unit-testable in CI. It must be verified manually against the linked project after `supabase db push`, and the result recorded in the worklog per CLAUDE.md's "manually verified and noted as such" rule. The specific checks:
1. Insert a wear → `wear_count = 1`, `last_worn_at` = that date, `cost_per_wear = purchase_price / 1`.
2. Insert a second wear on an earlier date → `wear_count = 2`, `last_worn_at` unchanged (it's `MAX`, not "latest inserted").
3. Update a wear's date to a later one → `last_worn_at` follows.
4. Delete all wears → `wear_count = 0`, `last_worn_at NULL`, `cost_per_wear = purchase_price`.
5. Duplicate same-day insert → unique violation / `ON CONFLICT` no-op, count unchanged.
6. As user A, attempt to insert a wear referencing user B's `item_id` → rejected (RLS `WITH CHECK` and/or the composite FK), and B's `wear_count` unchanged. **This is the cross-user integrity check — do not skip it.**
7. Delete the parent item → its wear rows are gone.

**`wardrobe.service.test.ts`** (additions): each new call hits the right table/endpoint with the right payload; `deleteWardrobeItem` issues a `DELETE` to `${EXPO_PUBLIC_BACKEND_URL}/wardrobe/items/{id}` with the bearer header; `markWardrobeItemWorn`'s old test is removed with the function.

**`wardrobe.queries.test.tsx`** (additions):
1. `useLogWardrobeItemWear` inserts a wear then reads back `wear_count`/`cost_per_wear`, returning them for the toast — it never computes `cost_per_wear` client-side.
2. `useLogWardrobeItemWear`/`useUpdateWardrobeItemWear`/`useDeleteWardrobeItemWear` each invalidate both the wears key and the grid keys.
3. `useToggleWardrobeItemFavourite` optimistically patches the cached items array and rolls back on error.
4. `useDeleteWardrobeItem` optimistically removes the item from the cached array and restores it on error.
5. `useSaveWardrobeItemDetails` writes only `brand`/`purchase_price`/`purchase_date`/`user_notes` — asserts `wear_count`, `last_worn_at`, and `cost_per_wear` are **absent** from the update payload.

**`ItemDetailSheet.test.tsx`** (modifications):
1. "Mark Worn" calls `useLogWardrobeItemWear` with today's date (no `wear_count` arithmetic anywhere).
2. Toast renders "Outfit logged! Cost per wear: ₹X" with the value returned by the mutation, and the no-price variant when `cost_per_wear` is null.
3. The "Worn N×" row opens the wear-history mode.
4. Delete passes the jwt through and dismisses the sheet on success.
5. Favourite toggle triggers the animated heart without waiting for the mutation to settle.

**`WearHistorySection.test.tsx`**:
1. Renders one row per wear, newest first, dates in `'en-IN'`.
2. Loading, error, and empty ("Never worn") states each render.
3. Editing a row's date calls `useUpdateWardrobeItemWear` with the new date.
4. First delete tap arms, second calls `useDeleteWardrobeItemWear`.
5. A duplicate-date save surfaces the friendly conflict message, not a raw Postgres error.

**`WearDateField.test.tsx`**: "Today"/"Yesterday" quick picks resolve to the correct IST dates; a future date is rejected; a date before `purchase_date` is rejected; malformed input is rejected without crashing.

**`WearLoggedToast.test.tsx`**: renders the message and auto-dismisses after `WEAR_TOAST_DURATION_MS` (fake timers).

**`EditItemTagsForm.test.tsx`** (additions): brand/price/date/notes prefill from the item; the notes counter tracks length and hard-stops at 500; price renders with `en-IN` grouping; Save calls both mutations and stays open (with an error) if the second fails.

**`test_wardrobe_router.py`** (additions): delete returns 200 and schedules the cleanup task with the row's three keys; 404 for an unknown/unowned id (and asserts no cleanup task is scheduled); 422 for a malformed UUID; 401 without a bearer token.

**`test_wardrobe_repository.py`** (additions): `delete_item` issues an RLS-scoped delete keyed by id.

**`test_wardrobe_deletion_service.py`** (new): calls `delete_objects` with only the non-null keys; swallows and logs a storage exception rather than raising.

**`test_r2_storage.py`** (addition): `delete_objects` passes the correct `Delete={"Objects": [...]}` shape and bucket.

**Not automatable this pass:** the 7 DB checks above (manual, against the linked project); real-device bottom-sheet behaviour for the new wear-history mode (`BL-010`/`BL-013`); actual R2 object disappearance after a delete (needs a live bucket check — worth doing once by hand during Developer/QA, given `BL-069`'s lesson that deployed-environment storage behaviour is invisible to this repo's checks).

## Open questions / blockers

1. **The raw ticket's AC #5 is superseded and cannot be satisfied as written.** `"Mark Worn" increments wear_count` conflicts with `BL-071`'s directive (wear_count becomes derived; a tap inserts a dated row). This design follows `BL-071`. The ticket's Status note ("no new schema, no new routes") is likewise stale — this ticket now adds both. Flagging rather than silently picking, per the rules; no action needed beyond acknowledging it at the gate.
2. **One wear per item per day (`UNIQUE (item_id, worn_on)`) is an Architect call, not a user decision.** It directly fixes the "unbounded taps inflate the count" complaint and makes the tap idempotent, but it makes "wore it twice in one day" unrecordable. Confirm, or say the word and the constraint is dropped in favour of allowing duplicates (which reopens the mis-tap problem in a different shape).
3. **The backfill is lossy and irreversible.** Any item with `wear_count > 1` from SS-014 taps collapses to a single wear row on its `last_worn_at`; items with a count but no date reset to 0. Assessed as safe because all existing wear data is your own pre-launch test taps against the single shared project (`BL-003`), but this is a one-way door (`OPERATOR_RULEBOOK.md` §C2) — needs an explicit nod before `supabase db push`.
4. **Date entry ships without a picker library** (quick-picks + validated `DD/MM/YYYY` input) to avoid a new native dependency on a web-first app. If a real calendar picker is wanted, that's a follow-up, not a silent addition here.
5. **`purchase_price` unit: paise (per the schema comment) or rupees (per SS-014's shipped UI and this ticket's AC)?** Money semantics, needs a decision — it determines both what the edit form writes and whether every `cost_per_wear` value in the DB is off by 100×. This design assumes **whole rupees** (matching what's already shipped and what the AC's `₹1,23,456` example implies) and corrects the stale column comment; logged as `BL-075` so the same ambiguity in `shopping_wishlist.current_price`/`target_price` doesn't rot. Overridable at the gate.
6. **Backend must be running locally for delete to work** (`BL-037` — no deployment exists). Delete is the first destructive action routed through FastAPI; on a machine without `uvicorn` up, deleting an item now fails where it previously succeeded. Accepted (consistent with `remove-bg`/`tag`/`image-url`), flagged so it isn't a surprise during manual verification.
7. **File overlap with SS-019** (fix SS-013 upload-flow regressions, not started). Both tickets touch `mobile/features/wardrobe/components/`. Per CLAUDE.md's parallelization rule these are **not** independent — do not run them in concurrent worktrees; serialize.

## Backlog deltas

Moved to **Resolved**:
- `BL-071` (schema) — **resolved by this design.** The directive is implemented as specified: `wardrobe_item_wears` table + migration 006, per-wear rows the user can view/edit/delete, `wear_count`/`last_worn_at` demoted to trigger-maintained caches, `cost_per_wear` left untouched as a `GENERATED` column (and explicitly the reason a trigger was chosen over a view).
- `BL-068` (infra, was Parked) — **resolved by this design.** Item delete now goes through `DELETE /wardrobe/items/{item_id}`, which captures the item's three R2 keys before removing the DB row and then deletes them via an async `BackgroundTasks` cleanup. Residual (best-effort failure) carried forward as `BL-074`, not left inside this row.

Updated, **not** resolved:
- `BL-036` (schema, read-then-write race) — **the `wear_count` instance is genuinely eliminated**, not merely accepted: there is no longer any client-computed increment to race, because the client only ever `INSERT`s an immutable dated row and the count is recomputed server-side by a trigger inside the same transaction (two concurrent inserts both count; a same-day duplicate collapses on the unique index rather than clobbering). Marked as a **candidate to resolve for wear-tracking specifically**. The row itself stays **Active** — its original subject (`users.style_preferences`, SS-007) and its sibling `BL-066` (`ai_tags`) are untouched and still do read-then-write.
- `BL-004` (schema, Parked — re-scanned per `BL-071`'s directive) — clarifying note only, row not moved (Parked is `/audit`'s to reconcile). `wear_count` and `last_worn_at` now join `cost_per_wear` in the "must not be written by client code, but the generated TS types still type them as writable" class. Mitigated here by deleting the only client write path (`markWardrobeItemWorn`) and by `COMMENT ON COLUMN` markers in the migration — still not type-enforced.

New rows added to **Active**:
- `BL-074` (infra) — R2 cleanup on item delete is best-effort: if the background `delete_objects` call fails, the objects stay orphaned with no retry and no sweeper. Strictly better than the pre-SS-015 state (no cleanup at all) but not a guarantee; pair with `BL-056`'s durable-background-task gap when that's picked up.
- `BL-075` (schema) — money-unit ambiguity: `wardrobe_items.purchase_price` is commented "in paise" in `001_initial.sql` but treated as whole rupees by shipped UI and SS-015's AC; `shopping_wishlist.current_price`/`target_price` carry the same comment and no consumer yet. Needs one decision applied consistently before any real purchase data or any Razorpay-adjacent work.

## Risk: high

Justification: this ticket creates a new table, a new RLS policy, a trigger that writes to `wardrobe_items`, a `UNIQUE` constraint added to an existing table, and a **lossy, irreversible backfill** of existing wear data — every one of which is squarely inside CLAUDE.md's and `OPERATOR_RULEBOOK.md` §C2's `high` bar (schema/migrations, RLS, irreversible). It also changes the delete path from a client-side DB delete into a backend endpoint that permanently destroys R2 objects, and it touches a `GENERATED` column's input. The cross-user integrity surface is real and non-obvious: without the composite FK and the explicit `WITH CHECK`, a user could insert a wear row pointing at another user's `item_id` and corrupt that user's `wear_count` through the trigger — exactly the class of one-way-door defect the full lane exists to catch. Full lane: every gate preserved, and Open questions #2/#3/#5 in particular need answers before `supabase db push` runs.
