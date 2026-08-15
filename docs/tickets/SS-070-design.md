# SS-070 — Test-User Seed & Teardown Script — Design Note

`Tier: sketch` — design note, not a full doc. Ticket's Description/AC are sound and stand as written **except** the cascade claim in Technical Notes, corrected below.

## Ground-check (all `[VERIFIED 2026-08-15]` against this repo / installed venv)

- **`supabase-py` 2.31.0 / `supabase-auth` 2.31.0** (`backend/requirements.txt:81-82`), source at `backend/venv/Lib/site-packages/supabase_auth/_sync/gotrue_admin_api.py`: `create_user(attributes)` ← `AdminUserAttributes` TypedDict with `email` / `password` / `email_confirm: bool` / `app_metadata` (`types.py:244-280`); `list_users(page=None, per_page=None) -> List[User]`; `delete_user(id, should_soft_delete=False)` (default = **hard** delete); `get_user_by_id(uid)`; `generate_link(params) -> GenerateLinkResponse` with `.properties.hashed_token` / `.email_otp`. Ticket's assumed names are correct.
- **`list_users` has no server-side filter** — page/per_page only. So `list`/`delete` must page client-side until a short page and filter locally on prefix **and** `app_metadata` marker. Confirms the ticket's paging edge case; fine at today's user count.
- **CORRECTION — `public.users` has NO FK to `auth.users`.** `001_initial.sql:25` is `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`; grep across all 20 migrations finds no `REFERENCES auth.users`. `002`'s trigger populates the row, nothing links it. **`auth.admin.delete_user` therefore leaves `public.users` + `wardrobe_items` fully orphaned.** Ticket Technical Note ("cascades via the FK from `001_initial.sql`") is wrong — AC #6's verification query is what would have caught this in production.
- **Delete order that actually works:** `DELETE FROM public.users WHERE id=<uid>` (cascades `wardrobe_items`, `outfits`, `ai_cost_ledger` 012:32, `suggestion_impressions` ×2 013:116/151) **then** `auth.admin.delete_user(uid)`. Four tables reference `users(id)` with **no** `ON DELETE` action → they **block** the delete: `suggestion_sessions` (001:99), `user_avatars` (001:111), `social_posts` (001:121), `shopping_wishlist` (001:136). `suggestion_sessions` gets written whenever the test user uses the suggestion flow — i.e. the realistic case — so `delete` must explicitly clear these four first, or it fails with a raw FK error on exactly the accounts that were actually used.
- **`wardrobe_items` seed shape:** `image_url` NOT NULL (use a placeholder URL — never R2, per the ticket's leak edge case); `category` is **nullable** since `005:20`; `processing_status` NOT NULL DEFAULT `'uploaded'` (`005:23`) — set `'bg_removed'` for a realistic row; `occasion_tags` is **`TEXT[]`** not the enum since `008:19`; `user_id`, `subcategory`, `color_primary`, `pattern`, `fabric`, `season_tags`, `brand`, `purchase_price` (paise, INTEGER). `cost_per_wear` is GENERATED — never insert it. Normalisation triggers (`008`, `016`) fire on insert; seed values must be real registry values.
- **`session` install target:** `mobile/lib/supabase.ts:33-39` uses default `storageKey` with `persistSession: true`, web adapter → `localStorage`. Snippet key is `sb-<project-ref>-auth-token`, ref derived from `SUPABASE_URL` — same value the destructive-confirm prompt prints.

## Design decisions

- **`session` uses `sign_in_with_password` (anon key), not `generate_link` redemption.** `create` already sets a password with `email_confirm=True`, and `BL-174` confirms email confirmation is off — so password sign-in returns a `Session` directly, one call, no token-redemption step. Keep `generate_link` as fallback only. Simpler and it exercises the same path SS-072 will ship.
- **Env/secrets:** `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` from environment only, matching `backend/scripts/ss035_verify_wear_occasion.py:70-72`. Never printed, never in tracebacks (catch and re-raise with a scrubbed message).
- **Guardrails (§C6 — all mandatory, none optional at sketch tier):** (1) every subcommand aborts unless `STYLESENSE_ALLOW_TEST_USER_ADMIN=1`; (2) `delete` refuses any email not matching the `stylesense-test+` prefix **and** missing the `app_metadata` marker — both, not either; (3) no subcommand accepts a raw user id as a delete target, label only; (4) destructive subcommands print the project ref and require confirmation; (5) `create` pre-checks `public.users` for the email (the `BL-169` landmine) and refuses a duplicate label before calling the Admin API; (6) prefix constant documented in the docstring as a safety device, not a config knob.

## Files

- Create `backend/scripts/ss070_test_users.py` (standalone, not imported by `app.main` — matches existing `scripts/` precedent).
- Create `backend/tests/test_ss070_test_users.py`.

## Test plan (`backend/tests/test_ss070_test_users.py`, Admin client faked — no live calls, AC #9)

- missing `STYLESENSE_ALLOW_TEST_USER_ADMIN` blocks **every** subcommand (parametrised over all five).
- `delete` refuses an email without the test prefix — asserts refusal message and that `delete_user` was never called.
- `delete` refuses an account with the right prefix but **no** `app_metadata` marker (the both-not-either rule).
- `create` with an existing label refuses instead of creating a second account.
- `list` filters a faked mixed page (test accounts + a real developer account) down to only the marked ones — zero false positives.
- `list` pages: faked full first page + short second page returns the union, not just page 1.
- `delete` clears the four non-cascading tables before `public.users`, and `public.users` before `auth.users` — assert call order.
- `service_role` key never appears in any captured stdout/stderr or raised exception text.

## Edge cases

Carried from the ticket unchanged: wrong project, R2 objects not cleaned up (seed with placeholder URLs — preferred option taken above), session artifact expiry (fail with "expired, re-run `session --label`"), partial create / `BL-169` half-state, concurrent `create` racing on the email unique constraint, `list` paging truncation, hand-edited prefix constant. Added from ground-check: **`delete` blocked by the four no-action FKs** (above), and **`auth`-only delete leaving orphaned `public.users`/`wardrobe_items`** — the failure mode AC #6 exists to catch, now known to be real rather than hypothetical.

## Open questions / blockers

- **None blocking.** Runs locally against the live project via Admin API, same as every other `backend/scripts/` script — `BL-037` (no backend deployment) and `BL-171` (no hosted build) don't apply; `BL-001` (phone auth) and `BL-047` (no EAS project) are untouched by this ticket.
- **`BL-167` (no sign-out) — relationship, not resolution.** The `session` subcommand is a *workaround* for the absence of sign-out: it installs a session directly, bypassing the missing UI. Switching between test users on one device still requires clearing `localStorage` by hand until SS-071 ships. Row stays open.
- AC #4 and AC #5 are **manual-verification** criteria by construction (they require a real browser and a project containing the developer's real account). They cannot be covered by CI tests — QA must record them as manually verified in the worklog per CLAUDE.md's testing rule.
- New: **`BL-175`** logged (Active, `schema`) — the missing `public.users` → `auth.users` FK is an app-wide gap, not just this script's problem; any future delete-account feature hits it too. Out of scope here (this script compensates in application code); flagged rather than silently fixed, since adding that FK is a migration on live auth-adjacent schema.

**Verdict: `Risk: high` — confirmed, unchanged.** Reads `service_role`, and performs irreversible multi-table deletes on the one shared live project that also holds the developer's real account; the ground-check found the ticket's own cascade assumption to be wrong, which is precisely the class of error that makes this a one-way door under §C2.

