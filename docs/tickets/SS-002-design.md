# SS-002 — Design: Supabase Project Setup & Database Schema Migration (Verification Pass)

## Scope restatement

This ticket asks for a Supabase project with the full StyleSense schema (7 tables, 3 ENUMs, computed `cost_per_wear`, GIN index on `occasion_tags`, RLS on every table), Phone Auth via MSG91, and generated TypeScript types consumed by the mobile app. Per the ticket's own "Status note," this work is **already largely done** (`init documents/handoff.md` Section 6, marked complete except 6.2). This design doc is therefore a verification/reconciliation pass: confirm the applied schema and generated types actually satisfy every AC line-by-line, rather than a from-scratch build plan. No new schema files should be authored unless a real gap is found below.

## Files to create/modify (verification steps, not new builds)

No new application files are expected. The Developer's job on this ticket is to **verify** the following against the AC and record results in the worklog — not to write new migrations or regenerate types unless a discrepancy is found.

1. **`supabase/migrations/001_initial.sql`** (exists, 189 lines) — verify against AC:
   - Confirm all 3 ENUMs (`wardrobe_category`, `plan_tier`, `occasion_type`) are declared with the exact value sets below.
   - Confirm all 7 tables exist: `users`, `wardrobe_items`, `outfits`, `suggestion_sessions`, `user_avatars`, `social_posts`, `shopping_wishlist`.
   - Confirm `cost_per_wear` is a `GENERATED ALWAYS AS (...) STORED` column on `wardrobe_items` with the exact `purchase_price / wear_count` (with `wear_count = 0` guard) logic.
   - Confirm `idx_wardrobe_occasions` is a `GIN` index on `wardrobe_items.occasion_tags`.
   - Confirm `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` appears for all 7 tables and each has a `user_owns_*`-style policy using `auth.uid() = user_id` (or `= id` for `users`).
   - **Gap found:** none of the `CREATE TYPE` / `CREATE TABLE` / `CREATE INDEX` / `CREATE POLICY` statements use `IF NOT EXISTS` (or `CREATE POLICY IF NOT EXISTS` equivalent, which Postgres doesn't support natively — would need `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` wrapping). This violates the ticket's own Technical Note ("Migration must be idempotent"). Since the migration has already been applied once successfully, this is not a live blocker, but re-running `001_initial.sql` against the same database today will fail with "already exists" errors. Flag as a follow-up: either accept the migration as one-shot/historical (no re-run needed) or add idempotency guards before any future re-application (e.g., in a fresh preview/staging Supabase project). Do not silently rewrite the file as part of this verification pass — this is app/infra-adjacent and out of this ticket's stated scope unless the user confirms they want the migration file edited.

2. **`mobile/types/supabase.ts`** (exists, 695 lines, generated) — verify field-for-field against `001_initial.sql`:
   - `Database["public"]["Tables"]` contains all 7 tables with matching Row/Insert/Update shapes (nullable vs. required matches nullable vs. `NOT NULL` in SQL).
   - `Database["public"]["Enums"]` contains `occasion_type`, `plan_tier`, `wardrobe_category` with value lists identical to the SQL ENUM definitions.
   - `wardrobe_items.cost_per_wear` is typed `number | null` in `Row` and is *absent as required* from `Insert` (present only as optional/omittable) since it is a generated column the client never writes — confirmed already optional (`cost_per_wear?: number | null`) in both `Insert` and `Update`, which is acceptable but note that Postgres will reject any write to a `GENERATED ALWAYS ... STORED` column, so callers must never pass `cost_per_wear` explicitly. No type-level enforcement exists to block this — flag as a soft risk for `features/wardrobe/*.service.ts` code in later tickets, not something to fix here.
   - `mobile/lib/supabase.ts` imports `Database` from `../types/supabase` and the import path resolves (confirmed at `mobile/lib/supabase.ts:3`).

3. **Supabase project itself** (`mefpfykuinasgkpfhmzk`, region `ap-south-1`, confirmed in `supabase/.temp/linked-project.json`) — verify live state matches the file-based migration:
   - Since no MCP/CLI access is available to this Architect pass, the Developer phase must run `supabase db diff` (or inspect via Supabase Studio / Table Editor) against the linked project to confirm the live schema matches `001_initial.sql` exactly (no drift from manual dashboard edits).
   - Confirm RLS is actually **enabled** at the database level (not just present in the migration file) — `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` can be run but later disabled manually; verify via `pg_tables`/Studio "RLS enabled" toggle.
   - Confirm Phone Auth provider status in Supabase Studio → Authentication → Providers (see Open Questions — expected to be OFF/unconfigured).

4. **Type generation reproducibility** — confirm `supabase gen types typescript --project-id mefpfykuinasgkpfhmzk --schema public` (run from an authenticated CLI session) produces output identical (or only cosmetically different, e.g. comment headers) to the committed `mobile/types/supabase.ts`, proving the committed file is not stale relative to the live DB.

No new files under `app/`, `features/`, `components/ui/`, or `ai/` are implicated by this ticket — it is pure data-layer/infra.

## Concrete values to use, not invent

These are already fixed in `supabase/migrations/001_initial.sql` — transcribe/verify against them, do not restyle or reinvent:

**`wardrobe_category` (21 values):**
`western_top`, `western_bottom`, `western_dress`, `western_outerwear`, `ethnic_kurta`, `ethnic_saree`, `ethnic_lehenga`, `ethnic_anarkali`, `ethnic_salwar_kameez`, `ethnic_dupatta`, `ethnic_sherwani`, `indo_western`, `footwear_formal`, `footwear_casual`, `footwear_ethnic`, `footwear_sports`, `accessory_bag`, `accessory_jewellery`, `accessory_watch`, `accessory_belt`, `accessory_scarf`

**`plan_tier` (3 values):** `free`, `premium`, `premium_annual`

**`occasion_type` (12 values):**
`office`, `casual`, `date_night`, `wedding_guest`, `festival`, `puja`, `party`, `travel`, `workout`, `beach`, `formal_event`, `college`

**`cost_per_wear` formula (wardrobe_items):**
```sql
cost_per_wear NUMERIC GENERATED ALWAYS AS (
  CASE WHEN wear_count > 0
    THEN purchase_price::numeric / wear_count
    ELSE purchase_price
  END
) STORED
```

**RLS policy naming convention already in use:** `user_owns_profile`, `user_owns_wardrobe`, `user_owns_outfits`, `user_owns_sessions`, `user_owns_avatar`, `user_owns_wishlist`, plus `social_posts_public_read` / `social_posts_owner_write` for the one table with a public-read carve-out. All use `auth.uid() = user_id` except `users` which uses `auth.uid() = id`. Do not invent different policy names — the AC references `user_owns_*` as the naming pattern and it is already satisfied.

**Supabase project reference (confirmed live):** `mefpfykuinasgkpfhmzk`, region `ap-south-1` (per `supabase/.temp/linked-project.json` and `init documents/handoff.md` Section 6).

## Edge cases

Carried forward from the ticket:
- MSG91 DLT registration rejection: Twilio should be configured as fallback but not activated. **Not yet done at all** — see Open Questions.
- `service_role` key must never appear in client code — verify `mobile/` has no references to a service role key (only `EXPO_PUBLIC_SUPABASE_ANON_KEY` should appear in `mobile/lib/supabase.ts`, confirmed correct as of this read).

New edge cases observed from current codebase state:
- The migration file is not idempotent (see gap above) — re-running it against a database that already has the schema will throw `type "wardrobe_category" already exists` etc. This matters if a fresh Supabase **staging/preview project** is ever provisioned per the `develop` branch environment row in `CLAUDE.md`'s Deployment Environments table — right now there is only one linked project referenced in `.temp/linked-project.json`, with no visible distinction between a staging and prod Supabase project. Flag this as an open question below.
- `cost_per_wear` being a generated column means any `INSERT`/`UPDATE` from `features/wardrobe/*.service.ts` that accidentally includes `cost_per_wear` in the payload will cause a Postgres error at write time, not a TypeScript compile error, since the generated types mark it as optional rather than disallowed. Backend/frontend service code in later wardrobe tickets should explicitly omit this field when constructing insert/update payloads.
- `purchase_price` is stored as `INTEGER` (paise per the comment), but nothing in the schema or types enforces non-negative values — a negative `purchase_price` would silently produce a negative `cost_per_wear`. Not in scope to fix here; flag for the wardrobe-item-creation ticket's validation layer.

## Test plan

This is a schema/config ticket, not application logic, so tests are schema-verification tests + a couple of type-level asserts rather than component/hook tests. Suggested additions:

- `backend/tests/test_db_schema.py`:
  - `test_all_seven_tables_exist` — connects to the Supabase Postgres instance (or a local Supabase Docker instance per `CLAUDE.md`'s Local environment row) and asserts `users`, `wardrobe_items`, `outfits`, `suggestion_sessions`, `user_avatars`, `social_posts`, `shopping_wishlist` are all present in `information_schema.tables`.
  - `test_enums_have_full_value_set` — asserts `wardrobe_category` has 21 values, `plan_tier` has 3, `occasion_type` has 12, matching the exact lists above (via `pg_enum`/`information_schema`).
  - `test_rls_enabled_on_all_tables` — asserts `relrowsecurity = true` (via `pg_class`) for all 7 tables.
  - `test_wardrobe_occasion_tags_gin_index_exists` — asserts an index of type `gin` exists on `wardrobe_items.occasion_tags` (via `pg_indexes`/`pg_index`).
  - `test_cost_per_wear_computed_correctly` — inserts a `wardrobe_items` row with `purchase_price=1000, wear_count=4` and asserts `cost_per_wear == 250`; inserts a second row with `wear_count=0` and asserts `cost_per_wear == purchase_price` (matching the `ELSE purchase_price` branch).
  - `test_rls_denies_cross_user_read` — using two distinct authenticated test JWTs (or the anon key + `auth.uid()` mocking pattern already used elsewhere in `backend/tests/`), asserts user A cannot `SELECT` user B's `wardrobe_items` row.
- `mobile/__tests__/types/supabase-types.test.ts` (lightweight, compile-time-focused):
  - A `tsd`/type-only assertion (or simple runtime shape check against a mocked row) confirming `Database["public"]["Enums"]["wardrobe_category"]` has exactly 21 literal members and `occasion_type` has exactly 12 — guards against silent drift if the enum is edited in SQL but types aren't regenerated.
  - A test asserting `mobile/lib/supabase.ts`'s exported `supabase` client is constructed with the `secureStoreAdapter` (storage) and `persistSession: true` — this doesn't test SS-002's AC directly but protects the foundation SS-003 depends on; note this test belongs conceptually to SS-003, only add it here if the Developer finds `lib/supabase.ts` itself lacks any coverage yet.

Do not write tests asserting Phone Auth OTP delivery in this ticket — that cannot be tested until MSG91 (or Twilio) is actually configured (see below), and belongs to SS-003 in any case.

## Open questions / blockers

1. **Phone Auth / MSG91 is not configured — blocks SS-003, and technically fails this ticket's own AC.** `init documents/handoff.md` Section 6.2 and this ticket's Status note both confirm Phone Auth + MSG91 was explicitly skipped (requires DLT registration, 1-3 business days, plus funding). This means:
   - AC line "Phone Auth enabled; OTP to +91 test number delivers within 10 seconds" is **not satisfied** and cannot be verified end-to-end right now.
   - SS-003 ("Depends on: SS-002") explicitly depends on this. SS-003's own Status note already acknowledges this and instructs its Architect pass to design against Supabase's Phone Auth abstraction generically, without assuming OTP delivery works. This SS-002 design doc reconfirms: **do not mark the Phone Auth AC as done in the SS-002 worklog.** Recommend the worklog explicitly record this AC as "deferred by user choice, tracked as a known gap" rather than "complete."
   - Decision needed from the user: proceed with MSG91 DLT registration now (1-3 business day lead time), or activate the Twilio fallback mentioned in the ticket's Edge Cases section as an interim provider so SS-003 can be built and tested end-to-end sooner. This is a product/cost decision outside the Architect's authority to resolve — flagging only.

2. **Migration idempotency gap.** `001_initial.sql` doesn't use `IF NOT EXISTS` guards despite the ticket's Technical Note requiring it. Since the migration is already applied to the one live project, this isn't currently blocking, but it means the file can't be safely re-run to provision a second (e.g., staging) Supabase project without manual edits. Recommend the user decide whether a separate Supabase **staging** project (per `CLAUDE.md`'s `develop` → "Supabase staging project" row) actually exists yet — nothing in the repo currently distinguishes a staging project ref from the one prod-looking ref (`mefpfykuinasgkpfhmzk`) found in `supabase/.temp/linked-project.json`. If staging and prod are currently the same project, that's a deployment-environment gap worth surfacing to the user, not something to silently fix here.

3. **RLS live-state verification requires DB access the Architect pass doesn't have.** This design doc specifies what to check (see "Files to create/modify" item 3) but the actual verification — confirming RLS is enabled at the database level and policies are exactly as written in the migration file, with no drift from manual dashboard changes — must happen in the Developer phase with real Supabase credentials/CLI access.

4. **Generated-column write-safety** is a type-system gap (`cost_per_wear` and any other `GENERATED ALWAYS` column is optional rather than banned in the TS `Insert`/`Update` types). Not a blocker for this ticket, but worth a note for whoever builds `features/wardrobe/wardrobe.service.ts` later so they don't pass this field on insert.
