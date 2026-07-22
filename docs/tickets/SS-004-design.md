# SS-004 — Design: User Onboarding Wizard (4-Step, Skippable)

## Addendum — 2026-07-13 revision (option taxonomies moved to DB-backed reference tables)

**What changed and why**: after this design doc's original Architect pass, a user design review resulted in `docs/tickets/raw/SS-004.md`'s Technical Notes gaining a new requirement: `style_keywords`, `occasion_types` (Step 3's 9 UI occasion-priority options), and the 12-swatch `colour_palette` (Step 4) must **not** ship as hardcoded TS unions. These are the three lists most likely to expand post-launch (new regional festivals, new aesthetic categories — ethnic wear is first-class per CLAUDE.md, not an edge case), so they now ship as DB-backed reference tables (`key`, `label`, `sort_order`, `active`, plus `hex` for `colour_palette`), fetched once by the client and cached via React Query with a long `staleTime`. `gender`, `wardrobe_type`, and `budget_range` stay exactly as originally designed — hardcoded TS unions in `onboarding.constants.ts` — per the same Technical Note explicitly calling these three "structurally stable."

This is an **in-place revision**, not a rewrite: original reasoning that's still fully valid (incremental-save design, the FlashList pager analysis, BL-008/BL-022/BL-023 backlog reasoning, the top-50-cities list, the gender/wardrobe-type/budget-range values, the `style_preferences` JSONB shape) is unchanged below. Wherever this doc previously described `STYLE_KEYWORDS`/`OCCASION_PRIORITY_OPTIONS`/`PLACEHOLDER_COLOUR_PALETTE` as static TS constants, that has been edited in place to reflect the DB-fetched approach — sections below are the current, authoritative version, not a diff to mentally apply.

Sections touched by this revision: **Files to create/modify** (new migration, new taxonomies service + query hook, narrowed `onboarding.constants.ts`, widened `onboarding.types.ts`, updated Step2/3/4 components, new `TaxonomyChipsSkeleton` component, new/updated test files), **Concrete values** (new DB schema + seed SQL for the three tables, replacing the old static-array transcriptions with the same values as seed rows), **Edge cases** (loading/error/empty states for the taxonomies fetch), **FlashList pager** (explicit confirmation `getItemType` is unaffected), and **Test plan**.

No `docs/BACKLOG.md` changes were made as part of this revision pass — per the instruction for this pass, that bookkeeping was handled directly by the orchestrating conversation. BL-022 (placeholder colour palette, still unresolved) and BL-023 (Profile → Edit Preferences entry point missing) are unaffected by *where* the values are stored and remain exactly as logged in the original pass.

## Scope restatement

Build the 4-step onboarding wizard a phone-verified user lands on the first time they have no completed profile: Step 1 collects name/gender/city (searchable top-50-Indian-cities picker + "Other"), Step 2 collects multi-select style keywords + a single wardrobe-type description, Step 3 collects up to 3 occasion priorities from 9 options, and Step 4 collects a budget range plus up to 5 favourite colours from a 12-swatch palette. The wizard is a horizontal pager built on `FlashList` (per CLAUDE.md's standing "never `FlatList`" rule) with a step-indicator-dots header and a persistent Skip control, and it must be resumable: killing the app mid-wizard or explicitly skipping must not force a fresh restart from Step 1 with no memory of it, and a later, deliberate "Profile → Edit Preferences" entry point must reach the same wizard pre-filled. "Get Started" (Step 4's CTA) performs one write of the full `style_preferences` JSONB blob plus a new `onboarding_completed` flag to the `users` table. This ticket also has to close a real gap left open by SS-003 (tracked as BL-018): no DB mechanism currently creates a `public.users` row or tracks onboarding completion at all, so this design includes a schema migration and a rename of SS-003's row-existence heuristic to a real `onboarding_completed`-based check — without that, the wizard's own "kill app mid-onboarding" edge case has nothing to check against. **Per the 2026-07-13 revision above**: Step 2's style keywords, Step 3's occasion options, and Step 4's colour palette are fetched from three new DB-backed reference tables (not hardcoded TS unions) and cached client-side via React Query, so product can add/retire options without an app-store release; gender, wardrobe type, and budget range remain hardcoded TS unions, unchanged.

## Current codebase state (verified, not assumed)

- SS-003 has already merged and is live: `features/auth/{auth.service,auth.queries,auth.store,auth.types}.ts`, `hooks/{useAuth,useSmsAutoRead}.ts`, `app/(auth)/{login,verify-otp,onboarding}.tsx`, `app/(tabs)/{_layout,index}.tsx` all exist. `app/(auth)/onboarding.tsx` is exactly the disposable placeholder SS-003's Architect described — this ticket replaces its body entirely.
- `features/auth/auth.service.ts`'s `checkUserProfileExists(userId)` does `supabase.from('users').select('id').eq('id', userId).maybeSingle()` — row **existence**, not an `onboarding_completed` flag (there is no such column). `auth.queries.ts` wraps it as `useUserProfileExistsQuery`. `verify-otp.tsx` calls this after a successful verify and routes `false → /onboarding`, `true → /`.
- `supabase/migrations/001_initial.sql`'s `users` table (confirmed by direct read) has no trigger creating a `public.users` row on Supabase Auth signup, and no `onboarding_completed` boolean. `mobile/types/supabase.ts`'s generated `users` Row/Insert/Update types confirm the same — `style_preferences: Json | null` already exists (no migration needed for that field), but nothing tracks completion.
- `components/ui/Badge.tsx`'s `OccasionKey` type and `tokens.ts`'s `colors.occasion` only define 4 colours (`wedding`, `office`, `festival`, `casual`) — tracked as **BL-008**, still open. Step 3 needs 9 occasion options.
- No 12-colour fashion-palette token set exists anywhere in the design system (`components/ui/tokens.ts` only has UI-chrome colours: bg/accent/text/occasion) — this is a **new** gap, not previously logged.
- `app/(tabs)` has only `_layout.tsx` (the Auth Guard) and `index.tsx` (SS-008's smoke-test screen moved by SS-003). **No Profile tab exists** — SS-005 (Home Screen Shell + Bottom Tab Navigation, not yet built) is what will add a `profile.tsx`. This directly affects the "Can return to complete onboarding from Profile → Edit Preferences" AC — see Open Questions.
- `@shopify/flash-list@2.3.2` is already installed (`mobile/package.json`). Confirmed by reading `node_modules/@shopify/flash-list/dist/FlashListProps.d.ts` and `FlashListRef.d.ts` directly (v2's actual shipped API, not assumed from older docs) — see "FlashList pager" section below for exact behaviour.
- **(2026-07-13 revision)** No `style_keywords`/`occasion_types`/`colour_palette` reference tables exist in `supabase/migrations/001_initial.sql` or the (already-designed, not-yet-necessarily-applied) `002_onboarding_completed.sql` — confirmed by direct read of both. This revision's `003_onboarding_taxonomies.sql` (below) creates and seeds all three from scratch; it is not additive to an existing table.
- **(2026-07-13 revision)** `001_initial.sql` already defines a Postgres `ENUM TYPE occasion_type` (singular — `office`, `casual`, `date_night`, `wedding_guest`, `festival`, `puja`, `party`, `travel`, `workout`, `beach`, `formal_event`, `college`), used by `wardrobe_items.occasion_tags[]` / `outfits.occasion`. This revision's new `occasion_types` reference **table** (plural) is a deliberately distinct object for a distinct purpose (Step 3's onboarding UI vocabulary) — see "Concrete values" and "Open questions" below for why these aren't unified and why the near-identical name is flagged for a reviewer's second look.

## Files to create/modify

### New — `supabase/migrations/`

1. **`supabase/migrations/002_onboarding_completed.sql`** — resolves BL-018. Exact contents (transcribe, this is the concrete schema change this ticket needs), **unchanged by this revision**:

```sql
-- ============================================================
-- SS-004 — onboarding completion tracking + auto-provisioning
-- ============================================================

-- 1. Track onboarding completion explicitly (do not overload full_name
--    nullability as the signal — see docs/tickets/SS-004-design.md).
ALTER TABLE users
  ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT false;

-- 2. Auto-provision a public.users row whenever a new Supabase Auth user is
--    created (phone OTP signup creates an auth.users row on first
--    signInWithOtp/verifyOtp) — closes the gap SS-003's Architect flagged
--    (BL-018): nothing previously created this row, so SS-003's row-existence
--    heuristic never actually detected a "returning" user correctly.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id, phone, email)
  VALUES (NEW.id, NEW.phone, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();
```

Apply the same way `001_initial.sql` was applied (Supabase Dashboard → SQL Editor → Run), per this repo's existing convention. Note BL-002 (migrations not idempotent) — this migration has the same limitation as `001`; not fixed here, same acknowledged gap.

2. **`supabase/migrations/003_onboarding_taxonomies.sql`** *(NEW — 2026-07-13 revision)*. **Why a separate file rather than folding into `002`**: `002` addresses a distinct, already-fully-specified concern (auth/session completion tracking — column + trigger). `003` addresses reference-data creation and seeding, which is additive and carries its own non-idempotency risk (BL-002 — re-running `INSERT`s without a guard would duplicate/conflict on the primary key). Keeping them as separate files limits blast radius if one ever needs re-running or rolling back independently, and matches the one-concern-per-migration-file convention this repo already uses (`001` vs `002` are already split by concern, not merged). Exact contents (transcribe):

```sql
-- ============================================================
-- SS-004 (revision) — DB-backed option taxonomies
-- Resolves the ticket's Technical Notes update: style_keywords,
-- occasion_types, and colour_palette must not be hardcoded TS unions.
-- gender / wardrobe_type / budget_range are NOT moved here — they stay
-- as hardcoded unions in mobile/features/onboarding/onboarding.constants.ts
-- per the same Technical Note calling those three "structurally stable."
-- ============================================================

CREATE TABLE style_keywords (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  sort_order  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT true
);

-- NOTE: this table is a DISTINCT object from 001_initial.sql's `occasion_type`
-- ENUM TYPE (singular — used by wardrobe_items.occasion_tags[] / outfits.occasion,
-- the wardrobe-tagging vocabulary). This table (plural, `occasion_types`) is
-- Step 3's onboarding-wizard UI vocabulary — a different, freeform list that is
-- NOT FK'd to the enum and does not need to stay in sync with it (see
-- "Concrete values" below for the full reasoning, carried over from the
-- original pass). Named `occasion_types` per the ticket's own Technical Note
-- wording; flagged in "Open questions" below as a naming collision worth a
-- reviewer's explicit sign-off given how close it reads to the existing enum.
CREATE TABLE occasion_types (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  sort_order  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE colour_palette (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  hex         TEXT NOT NULL,
  sort_order  INTEGER NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT true
);

-- Reference data: readable by any authenticated user (the client fetches all
-- three tables client-side via the authenticated Supabase client, per
-- CLAUDE.md's "all user data queries MUST use authenticated Supabase client"
-- rule extended to shared reference data). Writable only via the Supabase
-- Dashboard / service_role — no client-side write path exists or is needed
-- for this ticket; that's the entire point (product edits these tables
-- directly to add/retire options without an app-store release).
ALTER TABLE style_keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE occasion_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE colour_palette ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_style_keywords" ON style_keywords
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_occasion_types" ON occasion_types
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_colour_palette" ON colour_palette
  FOR SELECT USING (auth.role() = 'authenticated');

-- Seed data: the SAME 9 style keywords, 9 occasions, and 12-swatch placeholder
-- palette this design doc has specified since the original pass (see
-- "Concrete values" below for the human-readable tables) — moved here as seed
-- rows instead of TS constants. Values are unchanged, only their storage
-- location moved.

INSERT INTO style_keywords (key, label, sort_order) VALUES
  ('ethnic',        'Ethnic',        1),
  ('western',       'Western',       2),
  ('indo_western',  'Indo-Western',  3),
  ('casual',        'Casual',        4),
  ('formal',        'Formal',        5),
  ('streetwear',    'Streetwear',    6),
  ('bohemian',      'Bohemian',      7),
  ('minimalist',    'Minimalist',    8),
  ('maximalist',    'Maximalist',    9);

INSERT INTO occasion_types (key, label, sort_order) VALUES
  ('office',   'Office',   1),
  ('wedding',  'Wedding',  2),
  ('festival', 'Festival', 3),
  ('casual',   'Casual',   4),
  ('date',     'Date',     5),
  ('party',    'Party',    6),
  ('college',  'College',  7),
  ('travel',   'Travel',   8),
  ('puja',     'Puja',     9);

-- BL-022 still applies, unchanged by this revision: 8 of these 12 are
-- unapproved placeholder hexes, 4 reuse already-approved brand accent hexes
-- (noted per row). Moving storage from a TS constant to a seed row does not
-- resolve BL-022 — swapping in a real, product-approved palette later is now
-- a seed-data update instead of a one-line TS constant edit, same
-- one-place-to-change property, still pending product sign-off.
INSERT INTO colour_palette (key, label, hex, sort_order) VALUES
  ('black',       'Black',            '#000000', 1),  -- placeholder
  ('white',       'White',            '#FFFFFF', 2),  -- placeholder
  ('maroon',      'Maroon',           '#7B241C', 3),  -- placeholder
  ('navy',        'Navy',             '#1B2A4A', 4),  -- placeholder
  ('royal_blue',  'Royal Blue',       '#2E5C8A', 5),  -- placeholder
  ('emerald',     'Emerald Green',    '#2D6A4F', 6),  -- = colors.accent.emerald (already approved)
  ('marigold',    'Marigold/Mustard', '#E8A420', 7),  -- = colors.accent.marigold (already approved)
  ('rose',        'Rose Pink',        '#C45B7C', 8),  -- = colors.accent.rose (already approved)
  ('beige',       'Beige',            '#D9C9A3', 9),  -- placeholder
  ('grey',        'Grey',             '#9A9590', 10), -- = colors.text.muted (already approved)
  ('pastel_blue', 'Pastel Blue',      '#A9C6E8', 11), -- placeholder
  ('red',         'Red',              '#C0392B', 12); -- placeholder
```

Apply after `002`, same Dashboard → SQL Editor → Run convention. Same BL-002 (non-idempotent) caveat applies — do not re-run without first checking whether the rows already exist.

3. **`mobile/types/supabase.ts`** — regenerate (`supabase gen types typescript`) or manually add: `onboarding_completed: boolean` to the `users` table's `Row`/`Insert`/`Update` types (`Insert`/`Update` as `onboarding_completed?: boolean` since it has a DB default); **and (2026-07-13 revision)** `Row`/`Insert`/`Update` types for the three new tables `style_keywords`, `occasion_types`, `colour_palette` (`key: string`, `label: string`, `sort_order: number`, `active: boolean`, plus `hex: string` for `colour_palette`). Do not hand-edit any other part of this generated file.

### New — `mobile/features/onboarding/`

4. **`onboarding.types.ts`** — `GenderKey`, `WardrobeTypeKey`, `BudgetRangeKey` (fixed TS unions, unchanged), `IndianCity { id: string; name: string; state: string; lat: number; lng: number }`, `StylePreferences` (the exact JSONB shape below), `OnboardingStepId = 'basic-profile' | 'style-wardrobe' | 'occasion-priorities' | 'budget-colours'`. **(2026-07-13 revision)** `StyleKeywordKey` and `OccasionPriorityKey` are widened from fixed unions to `type StyleKeywordKey = string` / `type OccasionPriorityKey = string` — their valid values now come from the DB (`style_keywords.key` / `occasion_types.key` where `active = true`), not a closed TS union, so the type can no longer statically enumerate them. Also add: `TaxonomyOption { key: string; label: string; sortOrder: number }`, `ColourPaletteOption extends TaxonomyOption { hex: string }`, `OnboardingTaxonomies { styleKeywords: TaxonomyOption[]; occasionTypes: TaxonomyOption[]; colourPalette: ColourPaletteOption[] }`.
5. **`onboarding.constants.ts`** — **(2026-07-13 revision, scope narrowed)**: keeps only the genuinely-static pieces — `GENDER_OPTIONS` (the 4-key gender list; note this was implicitly part of the original design's Step 1 but not explicitly listed as a constants-file export before this revision — making it explicit now), `WARDROBE_TYPES`, `BUDGET_RANGES`, `TOP_50_INDIAN_CITIES`. **Removed from this file**: `STYLE_KEYWORDS`, `OCCASION_PRIORITY_OPTIONS`, `PLACEHOLDER_COLOUR_PALETTE` — these three are no longer static exports; they come from `onboarding.taxonomies.service.ts` (below) at runtime. All remaining exact lists are specified below — transcribe, do not invent alternates.
6. **`onboarding.store.ts`** — Zustand store holding all in-progress wizard answers (not yet persisted) plus `currentStepIndex`. Typed selectors only. Includes capped toggle actions: `toggleOccasion(key)` no-ops past 3 selections (unless deselecting), `toggleColour(hex)` no-ops past 5 selections (unless deselecting). **(2026-07-13 revision)**: no logic change — `toggleOccasion`/style-keyword selection already operated on plain `string` keys passed in from whatever chip was pressed; only the *type* of those keys widens (`OccasionPriorityKey`/`StyleKeywordKey` → `string`, per `onboarding.types.ts` above), which is a type-level change only, not a behavioural one.
7. **`onboarding.service.ts`** — the only place besides `hooks/`/`features/auth` that calls `supabase.from('users')` for this domain (**unchanged by this revision** — this file is about writing/reading the `users` row, not the reference tables):
   - `saveStep1Profile(userId, { fullName, gender, city }): Promise<void>` — partial `update` on `users` (see "Incremental save" below for why this is a separate, earlier write).
   - `completeOnboarding(userId, data: StylePreferences): Promise<void>` — single `update` writing `style_preferences` (full JSONB) + `onboarding_completed: true`.
   - `fetchOnboardingProgress(userId): Promise<{ fullName, gender, city, stylePreferences } | null>` — reads back whatever's already saved, used to pre-fill the wizard on resume/edit-preferences re-entry.
8. **`onboarding.taxonomies.service.ts`** *(NEW — 2026-07-13 revision)* — kept as its own file rather than added to `onboarding.service.ts`, since it reads three shared reference tables with no `user_id` scoping at all (a different access pattern from every other method in `onboarding.service.ts`, which all key off `userId`):
   - `fetchOnboardingTaxonomies(): Promise<OnboardingTaxonomies>` — runs three `supabase.from(<table>).select('key, label, sort_order' [+ ', hex' for colour_palette]).eq('active', true).order('sort_order', { ascending: true })` queries via `Promise.all`, maps each table's rows to `TaxonomyOption[]` / `ColourPaletteOption[]` (snake_case `sort_order` → camelCase `sortOrder`), and returns the combined `OnboardingTaxonomies` object. If any of the three queries throws, the whole function rejects (no partial-success handling) — the query hook's `isError` state covers this uniformly for the caller rather than each step independently handling a subset failing.
9. **`onboarding.queries.ts`** — `useSaveStep1Mutation()`, `useCompleteOnboardingMutation()`, `useOnboardingProgressQuery(userId)`. **(2026-07-13 revision)** add `useOnboardingTaxonomiesQuery()`:
   ```ts
   export function useOnboardingTaxonomiesQuery() {
     return useQuery({
       queryKey: ['onboarding', 'taxonomies'],
       queryFn: fetchOnboardingTaxonomies,
       staleTime: 24 * 60 * 60 * 1000, // 24h — reference data changes rarely (product-edited, not user-edited); avoids a network round trip on every wizard entry within the same day
       gcTime: Infinity, // keep cached for the lifetime of the app session even if unmounted between steps
     });
   }
   ```
   The exact `staleTime`/`gcTime` values are an Architect judgment call, not a value fixed elsewhere in the repo — flagged explicitly in "Open questions" in case product/review wants a specific cache-bust policy (e.g. tied to app relaunch) instead.
10. **`components/StepIndicatorDots.tsx`** — 4 dots, active dot marigold (`bg-brand`), inactive `bg-textMuted`. Purely presentational (`currentIndex: number, total: number`).
11. **`components/ResumePrompt.tsx`** — shown before Step 1 when a returning user has `onboarding_completed: false` **and** already has a non-null `full_name` (i.e., got past Step 1 before abandoning). "Continue Setup" scrolls the pager to index 1 (Step 2) after pre-filling the store from `fetchOnboardingProgress`; "Skip for now" routes home. Not shown at all for a brand-new user (`full_name` still null) — they go straight into Step 1, nothing to resume.
12. **`components/CityPicker.tsx`** — `AppBottomSheet` (reused from `components/ui`, same pattern as SS-003's `CountryCodePicker`) containing an `Input variant="search"` filtering `TOP_50_INDIAN_CITIES` by name (case-insensitive substring), plus a final "Other" row. Selecting "Other" reveals an inline `Input variant="text"` requiring non-empty text before the wizard's "Next" is enabled (see Edge Cases — this is the one place BL-007's parked error colour is reused, not resolved).
13. **`components/TaxonomyChipsSkeleton.tsx`** *(NEW — 2026-07-13 revision)* — shared loading-state placeholder reused by Step2 (style keywords) and Step3 (occasions): renders `count` pill-shaped `Skeleton` instances (`components/ui/Skeleton`, `variant="text"`, custom `width`/`height` sized to a chip, e.g. `width={100} height={36}`) inside a `flex-row flex-wrap gap-2` wrapper, matching the eventual chip-row layout so there's no visible reflow/jump once real data arrives. Props: `{ count: number }`. Step 4's colour-swatch loading state is handled inline in `Step4BudgetColours.tsx` instead (12 `Skeleton variant="circle"` in the same 4×3 grid wrapper the real swatches use) since circles, not pills, need a different shape — not routed through this shared component.
14. **`components/Step1BasicProfile.tsx`** — name (`Input variant="text"`), gender (4 single-select `Badge` chips, neutral style + `selected`, sourced from `GENDER_OPTIONS` in `onboarding.constants.ts` — unaffected by this revision), city (`CityPicker` trigger + selected value display).
15. **`components/Step2StyleWardrobe.tsx`** — **(2026-07-13 revision)** calls `useOnboardingTaxonomiesQuery()` itself (see "Loading/error/empty state pattern" below for why each step owns this call rather than the wizard shell hoisting one call and prop-drilling it down). Renders `data.styleKeywords` as multi-select chips (`Badge`, neutral + `selected`) while `isSuccess`; renders `<TaxonomyChipsSkeleton count={9} />` while `isLoading`; renders an inline error message + "Retry" button (calling `refetch()`) when `isError`; renders an inline "No style options available right now" message when `isSuccess` but `data.styleKeywords.length === 0` (empty state). The 5 wardrobe-type chips (single-select) are unaffected — still sourced from the static `WARDROBE_TYPES` constant and render immediately regardless of the taxonomies query's state.
16. **`components/Step3OccasionPriorities.tsx`** — **(2026-07-13 revision)** same pattern as Step2: calls `useOnboardingTaxonomiesQuery()`, renders `data.occasionTypes` as multi-select chips capped at 3 (neutral `Badge` + `selected` — see BL-008 decision below, **not** occasion-coloured, unaffected by this revision), `<TaxonomyChipsSkeleton count={9} />` while loading, same error/retry and empty-state handling as Step2.
17. **`components/Step4BudgetColours.tsx`** — 4 budget chips (single-select, unaffected, still from static `BUDGET_RANGES`). **(2026-07-13 revision)** colour grid: calls `useOnboardingTaxonomiesQuery()`, renders `data.colourPalette` as the 12-swatch `flex-row flex-wrap` grid (each swatch `w-1/4` → 4 columns × 3 rows, capped multi-select at 5) while `isSuccess`; while `isLoading`, renders 12 `Skeleton variant="circle"` in the identical grid wrapper (not `TaxonomyChipsSkeleton` — circles, not pills, see item 13); same inline error/retry and empty-state (0 active colours) handling as Step2/3.

### New — `mobile/app/(auth)/`

18. **`mobile/app/(auth)/onboarding.tsx`** — replaces the SS-003 placeholder entirely. The wizard shell: reads `session.user.id` from `useAuthStore`, runs `useOnboardingProgressQuery` on mount to decide whether to show `ResumePrompt` first; renders `StepIndicatorDots` + a persistent "Skip" ghost button in a header row above the `FlashList` pager; footer row below the pager shows "Next" (steps 0–2, calls `saveStep1Profile` only when leaving step 0, otherwise just advances local `currentStepIndex`/scrolls) or "Get Started" (step 3, calls `useCompleteOnboardingMutation`, then `router.replace('/')`). **(2026-07-13 revision)** the shell itself does **not** call `useOnboardingTaxonomiesQuery()` — each of Step2/3/4 calls it independently (see item 15's cross-reference); no prop-drilling of taxonomy data through the shell is needed since React Query's shared `queryKey` cache means only the first of the three steps to mount triggers the actual network fetch (see "Loading/error/empty state pattern" below).

### Modified — `mobile/features/auth/` (closes BL-018's routing half)

19. **`auth.service.ts`** — rename `checkUserProfileExists` → `checkOnboardingCompleted(userId): Promise<boolean>`, query `supabase.from('users').select('onboarding_completed').eq('id', userId).maybeSingle()`, return `data?.onboarding_completed ?? false`. Same fail-safe-to-`false` behaviour on error (routes to `/onboarding`, never crashes the just-completed verify flow).
20. **`auth.queries.ts`** — rename `useUserProfileExistsQuery` → `useOnboardingCompletedQuery`, same shape otherwise.
21. **`app/(auth)/verify-otp.tsx`** — update the two renamed imports/call sites only; routing logic itself (`false → /onboarding`, `true → /`) is unchanged.

### New test files

22. `mobile/__tests__/features/onboarding/onboarding.store.test.ts`
23. `mobile/__tests__/features/onboarding/onboarding.service.test.ts`
24. `mobile/__tests__/features/onboarding/onboarding.taxonomies.service.test.ts` *(NEW — 2026-07-13 revision)*
25. `mobile/__tests__/features/onboarding/onboarding.queries.test.tsx`
26. `mobile/__tests__/features/onboarding/components/StepIndicatorDots.test.tsx`
27. `mobile/__tests__/features/onboarding/components/ResumePrompt.test.tsx`
28. `mobile/__tests__/features/onboarding/components/CityPicker.test.tsx`
29. `mobile/__tests__/features/onboarding/components/TaxonomyChipsSkeleton.test.tsx` *(NEW — 2026-07-13 revision)*
30. `mobile/__tests__/features/onboarding/components/Step1BasicProfile.test.tsx`
31. `mobile/__tests__/features/onboarding/components/Step2StyleWardrobe.test.tsx`
32. `mobile/__tests__/features/onboarding/components/Step3OccasionPriorities.test.tsx`
33. `mobile/__tests__/features/onboarding/components/Step4BudgetColours.test.tsx`
34. `mobile/__tests__/app/(auth)/onboarding.test.tsx` — replaces the SS-003 smoke test entirely (new assertions, see Test plan).

### Modified test files

35. `mobile/__tests__/features/auth/auth.service.test.ts` — update for the `checkUserProfileExists` → `checkOnboardingCompleted` rename (same test shape, new column asserted).
36. `mobile/__tests__/features/auth/auth.queries.test.tsx` — update for the `useUserProfileExistsQuery` → `useOnboardingCompletedQuery` rename.
37. `mobile/__tests__/app/(auth)/verify-otp.test.tsx` — update mocked hook name only.

No `backend/` files are implicated — same as SS-003, this is entirely client + Supabase, no FastAPI route.

## Loading/error/empty state pattern for the taxonomies fetch *(NEW section — 2026-07-13 revision)*

Per CLAUDE.md's standing rule ("ALWAYS handle loading, error, and empty states in every component"), and per the user's explicit instruction that this needs a real answer (not an improvised spinner) since Step 2 is the wizard's first interactive step depending on this fetch:

- **Loading**: `<TaxonomyChipsSkeleton count={N} />` (Step2/Step3) or 12 inline `Skeleton variant="circle"` (Step4) — reusing SS-008's `components/ui/Skeleton`, never an ad hoc spinner or blank space.
- **Error**: an inline message (e.g. "Couldn't load style options.") plus a "Retry" `Button variant="ghost"` that calls the query's `refetch()`. The rest of the step (and the wizard's Skip control) stays interactive — a failed taxonomies fetch must not block the user from skipping past a step whose chips didn't load.
- **Empty**: if the query succeeds but returns zero `active` rows for a given list (e.g. product deactivates every row by mistake), render an inline "No options available right now" message rather than an empty, confusing blank chip area. This is a real, if unlikely, state to guard given the RLS/seed design gives no DB-level guarantee at least one row stays active.

**Why each step calls the hook independently rather than the wizard shell calling it once and passing data down**: `useOnboardingTaxonomiesQuery()` uses one shared `queryKey` (`['onboarding', 'taxonomies']`) and its `queryFn` fetches all three tables in a single combined `Promise.all` call. Because of this, the *first* of Step2/3/4 to mount (Step 2, since it's first in pager order) triggers the one network fetch for all three lists at once; React Query's cache then serves Step 3 and Step 4 the same resolved data without a second network round trip. Each step independently owning the call (rather than the shell hoisting one call and prop-drilling `data.styleKeywords`/`data.occasionTypes`/`data.colourPalette` down through the `FlashList` pager's `renderItem`) keeps each step self-sufficient for its own loading/error/empty rendering, avoids a 2-level-deep prop-drilling chain, and costs nothing extra in practice since the cache is shared. Note also that `FlashList` may pre-mount an adjacent off-screen step for smooth paging depending on its internal windowing — if so, this is a beneficial side effect (the fetch may already be resolved by the time the user swipes to Step 3/4), not something this design needs to force via an explicit prefetch call in the wizard shell.

## FlashList pager — exact API, paging behaviour, and the tradeoff to flag for human review

**Verified against the actually-installed version** (`node_modules/@shopify/flash-list@2.3.2`'s shipped `.d.ts` files, not assumed from older FlashList v1 docs, since v1→v2 was a full internal rewrite):

- `FlashListProps<TItem>` extends `Omit<ScrollViewProps, 'maintainVisibleContentPosition'>` — so `horizontal` and `pagingEnabled` are both passed straight through to the underlying native `ScrollView`. Paging is native `ScrollView` paging (snap-to-full-width), not a FlashList-specific reimplementation.
- **v2 has no `estimatedItemSize`/`estimatedListSize` prop at all** (confirmed absent from `FlashListProps.d.ts`) — v2's RecyclerView-based engine auto-measures, unlike v1 which required a size estimate. Do not add either prop; it doesn't exist on this version and would be a TypeScript error.
- `ref` exposes `FlashListRef<TItem>` (confirmed in `FlashListRef.d.ts`): `scrollToIndex({ index, animated })` returns a `Promise<void>` — used for the `ResumePrompt`'s "Continue Setup" jump to index 1, and optionally for a tappable step dot (not required by the AC, but the ref supports it if the Developer wants it).
- `getItemType?: (item, index) => string | number` exists specifically to improve/control recycling. **This must be set** to each step's unique `id` (`'basic-profile'`, `'style-wardrobe'`, `'occasion-priorities'`, `'budget-colours'`) so FlashList never attempts to recycle one step's rendered native view into another step's slot — with only 4 items and no 5th item of the same type ever entering the pool, this effectively means each step is rendered once and never recycled, sidestepping the class of bug where a `TextInput`'s focus/state gets reused across differently-typed cells.
  - **(2026-07-13 revision — explicit confirmation, per the instruction to double-check rather than just assert)**: does `getItemType` need any change now that Step2/3/4 depend on async data? **No.** The pager's list of items is still exactly the same 4 fixed step *descriptors* (`{ id: 'basic-profile' }`, `{ id: 'style-wardrobe' }`, `{ id: 'occasion-priorities' }`, `{ id: 'budget-colours' }`) regardless of what each step renders internally — `getItemType` operates on the pager's own 4-item array, keyed by each step's stable `id`, not on the taxonomies data those steps happen to fetch once mounted. Whether Step 2 renders its chips, a skeleton, or an error message is entirely internal to that step component's own render output; it doesn't change the identity, count, or type key FlashList sees for that pager slot. So `getItemType` is unaffected by this revision and does not need to key off anything taxonomy-related.
- **Why local component `useState` is not used for form values**: since each step's answers live in `onboarding.store.ts` (Zustand), not in the step component's own local state, even if FlashList *did* recycle/remount a step's view while scrolling back and forth, no user input would be lost — the value is read back from the store on every render, not from component-instance state. This is a deliberate mitigation, not incidental.
- Each step item must be wrapped in a `View` sized to the pager's exact width (`useWindowDimensions().width`, since NativeWind's `w-full` alone isn't guaranteed to equal the FlashList's own measured width in every layout scenario) for `pagingEnabled`'s one-page-per-swipe snap to be exact — a mismatch here is the most common source of "paging looks like it skips or gets stuck between two pages" bugs with this feature.
- `onMomentumScrollEnd`'s `nativeEvent.contentOffset.x / pagerWidth`, rounded, drives `currentStepIndex` in the store (for `StepIndicatorDots` and for gating "Next" vs. "Get Started" in the footer) when the user swipes manually rather than pressing "Next".

**Flagging for human review, per the explicit instruction to not silently substitute a simpler approach**: this is a **fixed 4-item list**, not a long virtualized feed — FlashList's core value proposition (view recycling across many more items than fit on screen) provides essentially no benefit here; all 4 steps could be pre-rendered by a plain `ScrollView horizontal pagingEnabled` with identical visual behaviour and less internal machinery (no recycling pool, no `getItemType` bookkeeping, no v1-vs-v2 API surface to track). CLAUDE.md's rule ("never use `FlatList` for large lists — use `FlashList`") is written in terms of `FlatList`'s specific replacement, and the ticket has been explicitly edited to require `FlashList` here regardless of list size — so this design proceeds with `FlashList` as instructed, but this tradeoff (added complexity for zero recycling benefit on a fixed 4-page pager) should be confirmed as an intentional, standing choice rather than something a future ticket "fixes" back to `ScrollView` without someone having actually decided it project-wide.

## Concrete values to use, not invent

### `style_preferences` JSONB shape — transcribed verbatim from the ticket's Technical Notes

```ts
interface StylePreferences {
  styles: StyleKeywordKey[];
  wardrobe_type: WardrobeTypeKey;
  occasions_priority: OccasionPriorityKey[]; // max 3
  budget_range: BudgetRangeKey;
  favourite_colours: string[]; // hex codes, max 5
  gender: GenderKey; // duplicated from users.gender — see note below, this is intentional per the ticket's exact shape, not a bug to "fix" by removing one copy
}
```
`gender` is written to **both** `users.gender` (existing top-level column) **and** duplicated inside `style_preferences.gender`, exactly as the ticket's Technical Note lists it. Do not deduplicate this away. **(2026-07-13 revision note)**: `StyleKeywordKey`/`OccasionPriorityKey` are now `string` (DB-backed keys), not fixed unions — see `onboarding.types.ts` above — but this JSONB shape itself is unchanged.

### Gender options (Step 1) — stored as keys, not display labels — **unchanged, hardcoded, per the ticket's revision explicitly calling this field structurally stable**

| Key | Label |
|---|---|
| `woman` | Woman |
| `man` | Man |
| `non_binary` | Non-binary |
| `prefer_not_to_say` | Prefer not to say |

### Style keywords (Step 2, multi-select) — **(2026-07-13 revision) now DB seed rows, not a TS constant** — see `003_onboarding_taxonomies.sql` above for the exact `INSERT` statements. Same 9 values as originally specified, transcribed here for reference:

`ethnic` (Ethnic), `western` (Western), `indo_western` (Indo-Western), `casual` (Casual), `formal` (Formal), `streetwear` (Streetwear), `bohemian` (Bohemian), `minimalist` (Minimalist), `maximalist` (Maximalist).

### Wardrobe types (Step 2, single-select) — **unchanged, hardcoded, per the ticket's revision explicitly calling this field structurally stable**

`mostly_western` (Mostly Western), `mostly_ethnic` (Mostly Ethnic), `equal_mix` (Equal Mix), `mostly_formal` (Mostly Formal), `mostly_casual` (Mostly Casual).

### Occasion priority options (Step 3, multi-select max 3) — **(2026-07-13 revision) now DB seed rows, not a TS constant** — see `003_onboarding_taxonomies.sql` above. Same 9 values, transcribed here for reference. **BL-008 explicitly addressed, not resolved**:

`office` (Office), `wedding` (Wedding), `festival` (Festival), `casual` (Casual), `date` (Date), `party` (Party), `college` (College), `travel` (Travel), `puja` (Puja).

**Decision**: BL-008 (logged by SS-008's Architect) flags that the design system's `Badge`/`OccasionKey` only defines 4 of these 9 as coloured occasion chips (`wedding`, `office`, `festival`, `casual`). This ticket does **not** invent the other 5 colours (`date`, `party`, `college`, `travel`, `puja`) — that's exactly the product/design decision BL-008 says is needed, and inventing them here would create the same "patchy 4-coloured-vs-5-neutral chips" inconsistency whether or not they happen to overlap with existing tokens. Instead, **all 9 of Step 3's chips render with `Badge`'s neutral style** (`occasion` prop omitted entirely), using only the `selected` boolean for the toggle state (marigold-bordered when active). This ships a visually consistent step today without pre-empting a product decision. BL-008 remains **open** — not resolved by this ticket. Note also that these 9 UI keys are a distinct vocabulary from the DB's `occasion_type` **enum** (`wedding_guest`, `date_night`, etc., used by `wardrobe_items`/`outfits`) — `style_preferences.occasions_priority` is freeform JSONB, not FK'd to that enum, so no mapping between the two is needed or attempted here; do not try to cast these into `occasion_type`. **(2026-07-13 revision)**: this also means the new `occasion_types` reference **table** (this ticket's DB source for Step 3's chip labels) is itself a third, related-but-separate vocabulary from both the enum and the JSONB values — all three happen to share most of the same string keys by design/convenience, but none of the three is mechanically derived from another. Flagged again in "Open questions" below given how easy this is to conflate.

### Budget ranges (Step 4, single-select) — stored as keys — **unchanged, hardcoded, per the ticket's revision explicitly calling this field structurally stable**

`500_1000` (₹500–1k), `1000_3000` (₹1k–3k), `3000_10000` (₹3k–10k), `10000_plus` (₹10k+). Labels transcribed verbatim from the ticket — do not reformat into full Indian-digit-grouped currency (CLAUDE.md's ₹1,23,456 formatting rule applies to actual rupee amounts elsewhere in the app, not to these fixed shorthand range labels).

### Colour palette (Step 4, 12 swatches, multi-select max 5) — **(2026-07-13 revision) now DB seed rows, not a TS constant** — see `003_onboarding_taxonomies.sql` above for the exact `INSERT` statement (includes `hex` per row). Same 12 values, transcribed here for reference — **new gap, flagged as placeholder, not a resolved token set, unaffected by the storage-location change**:

No 12-swatch general fashion-colour palette exists anywhere in the design system (`components/ui/tokens.ts` only defines UI-chrome colours). Rather than invent 12 arbitrary hex values with no product sign-off, this design reuses the 4 already-approved brand accent hexes where they double as recognisable fashion colours, and clearly labels the remaining 8 as a **placeholder**, mirroring the exact precedent already established in this codebase for `colors.accent.errorPlaceholder` (BL-007):

| Hex | Name | Source |
|---|---|---|
| `#000000` | Black | placeholder |
| `#FFFFFF` | White | placeholder |
| `#7B241C` | Maroon | placeholder |
| `#1B2A4A` | Navy | placeholder |
| `#2E5C8A` | Royal Blue | placeholder |
| `#2D6A4F` | Emerald Green | = `colors.accent.emerald` (already approved) |
| `#E8A420` | Marigold/Mustard | = `colors.accent.marigold` (already approved) |
| `#C45B7C` | Rose Pink | = `colors.accent.rose` (already approved) |
| `#D9C9A3` | Beige | placeholder |
| `#9A9590` | Grey | = `colors.text.muted` (already approved) |
| `#A9C6E8` | Pastel Blue | placeholder |
| `#C0392B` | Red | placeholder |

This is logged as **BL-022** (already appended in the original Architect pass; unchanged by this revision, since the gap is about the *values* needing product sign-off, not about where they're stored).

### Top 50 Indian cities (Step 1 city picker) — with approximate lat/lng for the weather API per the ticket's Technical Note — **unchanged, hardcoded, this is genuinely new app data, not a taxonomy the ticket's revision asked to move to the DB**

No exact list is fixed anywhere else in the repo; this is genuinely new app data, not a design token/schema/API contract, so providing a concrete, standard list here (rather than leaving the Developer to invent one ad hoc) avoids rework. Ranked by population/metro size (standard, non-controversial ordering):

```
Mumbai (Maharashtra) 19.0760,72.8777 · Delhi 28.7041,77.1025 · Bengaluru (Karnataka) 12.9716,77.5946 ·
Hyderabad (Telangana) 17.3850,78.4867 · Ahmedabad (Gujarat) 23.0225,72.5714 · Chennai (Tamil Nadu) 13.0827,80.2707 ·
Kolkata (West Bengal) 22.5726,88.3639 · Surat (Gujarat) 21.1702,72.8311 · Pune (Maharashtra) 18.5204,73.8567 ·
Jaipur (Rajasthan) 26.9124,75.7873 · Lucknow (Uttar Pradesh) 26.8467,80.9462 · Kanpur (Uttar Pradesh) 26.4499,80.3319 ·
Nagpur (Maharashtra) 21.1458,79.0882 · Indore (Madhya Pradesh) 22.7196,75.8577 · Thane (Maharashtra) 19.2183,72.9781 ·
Bhopal (Madhya Pradesh) 23.2599,77.4126 · Visakhapatnam (Andhra Pradesh) 17.6868,83.2185 ·
Pimpri-Chinchwad (Maharashtra) 18.6298,73.7997 · Patna (Bihar) 25.5941,85.1376 · Vadodara (Gujarat) 22.3072,73.1812 ·
Ghaziabad (Uttar Pradesh) 28.6692,77.4538 · Ludhiana (Punjab) 30.9010,75.8573 · Agra (Uttar Pradesh) 27.1767,78.0081 ·
Nashik (Maharashtra) 19.9975,73.7898 · Faridabad (Haryana) 28.4089,77.3178 · Meerut (Uttar Pradesh) 28.9845,77.7064 ·
Rajkot (Gujarat) 22.3039,70.8022 · Kalyan-Dombivli (Maharashtra) 19.2403,73.1305 · Vasai-Virar (Maharashtra) 19.4912,72.8054 ·
Varanasi (Uttar Pradesh) 25.3176,82.9739 · Srinagar (Jammu & Kashmir) 34.0837,74.7973 · Aurangabad (Maharashtra) 19.8762,75.3433 ·
Dhanbad (Jharkhand) 23.7957,86.4304 · Amritsar (Punjab) 31.6340,74.8723 · Navi Mumbai (Maharashtra) 19.0330,73.0297 ·
Prayagraj (Uttar Pradesh) 25.4358,81.8463 · Ranchi (Jharkhand) 23.3441,85.3096 · Howrah (West Bengal) 22.5958,88.2636 ·
Coimbatore (Tamil Nadu) 11.0168,76.9558 · Jabalpur (Madhya Pradesh) 23.1815,79.9864 · Gwalior (Madhya Pradesh) 26.2183,78.1828 ·
Vijayawada (Andhra Pradesh) 16.5062,80.6480 · Jodhpur (Rajasthan) 26.2389,73.0243 · Madurai (Tamil Nadu) 9.9252,78.1198 ·
Raipur (Chhattisgarh) 21.2514,81.6296 · Kota (Rajasthan) 25.2138,75.8648 · Guwahati (Assam) 26.1445,91.7362 ·
Chandigarh 30.7333,76.7794 · Thiruvananthapuram (Kerala) 8.5241,76.9366 · Bhubaneswar (Odisha) 20.2961,85.8245
```
Coordinates are approximate city-centre values, sufficient for a future weather-API lookup (this ticket does not call that API); the Developer should treat these as good-enough defaults, not survey-grade — no need to re-verify precision for this ticket's scope.

### Incremental save — why Step 1 is written early, and how the resume/skip/edit-preferences behaviours actually work together

The ticket's AC says "Get Started" saves "all data" — but the ticket's own edge case ("check `users.full_name IS NULL` to detect incomplete state; show a resume prompt") only makes sense if *something* is written before the final step, otherwise there is nothing to distinguish "never started" from "quit on step 3." Reconciling these:

- **Step 1's "Next"** immediately persists `full_name`, `gender`, `city` via `saveStep1Profile` (a small partial `update` — these already have dedicated top-level `users` columns, so this is cheap and doesn't touch `style_preferences` at all).
- **Steps 2–4** stay in `onboarding.store.ts` only; nothing is written to the DB until **"Get Started"** (Step 4's CTA), which writes the full `style_preferences` JSONB and flips `onboarding_completed: true` in one `completeOnboarding` call — satisfying the AC's "Get Started saves all data" literally for everything *except* the three fields already saved a step earlier.
- **Skip pressed on Step 1** (before "Next" was ever pressed): `full_name` stays `null`. Exiting routes home. Next login: `full_name IS NULL` and `onboarding_completed: false` → straight back into Step 1, no resume prompt (nothing to resume).
- **Skip pressed on Step 2, 3, or 4**: `full_name` is already non-null (Step 1's "Next" ran), `onboarding_completed` stays `false`. Exiting routes home. Next login: `full_name` non-null + `onboarding_completed: false` → `ResumePrompt` renders ("Continue Setup" jumps to Step 2, pre-filled; "Skip for now" routes home again) — this is the literal "resume prompt" the ticket's edge case asks for.
- **"Get Started"** completes: `onboarding_completed: true`. Every subsequent login routes straight home, no wizard, no prompt.
- **Profile → Edit Preferences** (once that entry point exists — see Open Questions #1): routes to `/onboarding` regardless of `onboarding_completed`'s value, pre-filled via `fetchOnboardingProgress`, always starting at Step 1 (not gated behind the resume-prompt logic, since this is a deliberate re-entry, not an automatic post-login routing decision).

### `Input`/`Badge` props this ticket reuses — do not restyle

- City "Other" free-text field: `Input variant="text" error={...}` using the same `colors.accent.errorPlaceholder` path SS-003 already established for validation errors — this ticket does **not** invent a second error colour. BL-007 remains open/parked, consumed as-is (same as SS-003's own framing).
- All chips: `Badge` with `onPress` + `selected`, `occasion` prop omitted everywhere in this ticket (see BL-008 decision above) — never pass an `occasion` key that isn't one of the 4 already defined in `OccasionKey`. **(2026-07-13 revision)**: this is unaffected by chip keys now coming from the DB rather than a TS union — the `Badge` component itself never receives an `occasion` prop for any of Step 3's chips regardless of where the key/label pair originated.

## Edge cases

Carried forward verbatim from the ticket:
- User kills app mid-onboarding → handled via the incremental-save + `ResumePrompt` design above (not a literal `full_name IS NULL` check alone — see reconciliation above for why the richer `onboarding_completed` + `full_name` combination is used instead of the literal single-column check the ticket names).
- User selects "Other" city but doesn't type anything → `Input`'s `error` prop is set, "Next" stays disabled, until non-empty text is entered (BL-007's parked placeholder colour, reused not resolved).
- Small screen (5-inch): 12 colour circles fit a 4×3 grid via `flex-row flex-wrap` with each swatch at `w-1/4` — no horizontal scroll inside the step (confirmed layout approach, not delegated to FlashList — this grid is a plain View inside Step 4, unrelated to the pager).

New edge cases found from the current codebase state:
- **Auto-provisioning trigger interaction with SS-003's routing heuristic**: once `002_onboarding_completed.sql` ships, a `public.users` row exists for every authenticated user immediately, which means SS-003's original row-existence check (`checkUserProfileExists`) would return `true` for every user, always — silently breaking the "first login vs. returning" distinction it was built for. This is why `auth.service.ts`/`auth.queries.ts` must be renamed to check `onboarding_completed` instead of row existence, not left alongside the new trigger unmodified.
- **Occasion cap UX (max 3, Step 3) and colour cap UX (max 5, Step 4)**: pressing a 4th/6th chip while already at the cap must not silently no-op with zero feedback — show a brief inline hint ("You can select up to 3 occasions" / "You can select up to 5 colours") rather than either blocking silently or auto-evicting the oldest selection (which would be surprising). This is an Architect decision, not stated in the ticket; flagging it as such.
- **`ResumePrompt` and Profile → Edit Preferences both target `/onboarding`, an `(auth)`-group route**: Expo Router allows navigating there from within the `(tabs)` group via an absolute path even while a session is active (the Auth Guard only gates `(tabs)`, not `(auth)`) — confirmed by reading `app/(tabs)/_layout.tsx`, no additional guard changes needed for this ticket.
- **Step 1's "Next" mutation failing (network error) must not silently strand the user on Step 1 forever** — `useSaveStep1Mutation`'s `onError` should surface an inline error (reusing the same `error` prop pattern) and keep "Next" pressable again, not advance the pager on a failed save (advancing without a successful write would defeat the entire incremental-save design above).

New edge cases from the 2026-07-13 revision (DB-backed taxonomies):
- **Taxonomies fetch fails (no network/RLS misconfiguration) after Step 1 already succeeded** — the user must not lose already-entered/saved Step 1 data or get stuck. Step 2/3/4 each show their own inline error + "Retry" (per the "Loading/error/empty state pattern" section above); the wizard's Skip control remains pressable regardless of the taxonomies query's state, so a user can still skip past a step whose options failed to load rather than being blocked entirely.
- **A reference table has zero active rows** (e.g. product deactivates every `colour_palette` row while adjusting the placeholder set) — treated as a distinct empty state, not an error: an inline "No options available right now" message, step remains skippable. This is a real possibility given nothing in the schema guarantees at least one row stays `active = true`.
- **Query result staleness across a long-lived app session**: with `staleTime: 24h`/`gcTime: Infinity`, a user who opens the app, does something else for hours, then returns to the wizard could see taxonomy options that were changed by product mid-session until the cache naturally expires or the app is fully restarted. Low-stakes for reference data like this (not a security or correctness issue, just a "product added a new occasion and this one user's session doesn't see it for up to a day" staleness window) — flagged as an accepted tradeoff of the chosen cache policy, not a defect.

## Test plan

`mobile/__tests__/features/onboarding/onboarding.store.test.ts`
- `toggleOccasion` selects up to 3, a 4th call when 3 are already selected is a no-op (still 3), deselecting an already-selected one always works regardless of count.
- `toggleColour` selects up to 5, a 6th call when 5 are already selected is a no-op.
- `setCurrentStepIndex`/wizard-answer setters update state; a typed selector returns the updated value.
- `reset()` clears all wizard-answer fields back to initial (used after a successful "Get Started").

`mobile/__tests__/features/onboarding/onboarding.service.test.ts`
- `saveStep1Profile`: mocks `supabase.from('users').update().eq()`, asserts it's called with exactly `{ full_name, gender, city }` (no `style_preferences` touched) and `.eq('id', userId)`.
- `completeOnboarding`: asserts the `update` call includes the full `style_preferences` object (all 6 keys incl. duplicated `gender`) and `onboarding_completed: true`.
- `fetchOnboardingProgress`: asserts a row with saved fields maps correctly; asserts a missing/null row resolves to `null` without throwing.

`mobile/__tests__/features/onboarding/onboarding.taxonomies.service.test.ts` *(NEW — 2026-07-13 revision)*
- `fetchOnboardingTaxonomies`: mocks `supabase.from('style_keywords'|'occasion_types'|'colour_palette').select().eq('active', true).order('sort_order', ...)`, asserts all three tables are queried and their rows mapped into `OnboardingTaxonomies` (camelCase `sortOrder`, `hex` present only on `colourPalette` entries).
- asserts rows are returned in the DB's `sort_order`-ascending order (no client-side re-sort assumed/needed given the query already orders).
- asserts a zero-row result for any one table resolves to an empty array for that key, not a thrown error (empty state, not an error state).
- asserts a thrown/rejected query (e.g. network failure on any of the three) causes the whole function to reject — no partial-success object is returned.

`mobile/__tests__/features/onboarding/onboarding.queries.test.tsx`
- `useSaveStep1Mutation`/`useCompleteOnboardingMutation`: mock `onboarding.service.ts`, assert `mutate`/`isPending`/`isError`/`isSuccess` wire through correctly.
- `useOnboardingProgressQuery`: `enabled: false` when `userId` is `undefined`.
- **(2026-07-13 revision)** `useOnboardingTaxonomiesQuery`: mocks `onboarding.taxonomies.service.ts`'s `fetchOnboardingTaxonomies`, asserts `isLoading` is true before resolution, `data` matches the mocked `OnboardingTaxonomies` shape on success, `isError` is true and `error` is populated when the mock rejects.

`mobile/__tests__/features/onboarding/components/StepIndicatorDots.test.tsx`
- renders 4 dots; the dot at `currentIndex` has the active (marigold) style, the rest do not.

`mobile/__tests__/features/onboarding/components/ResumePrompt.test.tsx`
- "Continue Setup" calls the provided `onContinue` callback (asserted, not a gesture-level scroll assertion — same precedent as SS-008/SS-003's BottomSheet/CountryCodePicker tests).
- "Skip for now" calls `onSkip`.

`mobile/__tests__/features/onboarding/components/CityPicker.test.tsx`
- typing a search query filters the 50-city list to matching names (case-insensitive substring).
- selecting "Other" reveals the free-text input; selecting a real city closes the sheet and reports the city name via a callback.

`mobile/__tests__/features/onboarding/components/TaxonomyChipsSkeleton.test.tsx` *(NEW — 2026-07-13 revision)*
- renders exactly `count` `Skeleton` instances (`testID="skeleton"`, per `components/ui/Skeleton`'s existing testID convention) for a given `count` prop.

`mobile/__tests__/features/onboarding/components/Step1BasicProfile.test.tsx`
- selecting each of the 4 gender chips toggles `selected` (single-select — selecting a second deselects the first).
- "Other" city with empty text disables/blocks proceeding (asserts the error path, not full navigation — the actual "Next" gating lives in the wizard shell, this test asserts the field-level error state).

`mobile/__tests__/features/onboarding/components/Step2StyleWardrobe.test.tsx`
- **(2026-07-13 revision)** mocking `useOnboardingTaxonomiesQuery` as `isLoading: true`: renders `TaxonomyChipsSkeleton`, not the chip row.
- **(2026-07-13 revision)** mocking it as `isError: true`: renders the inline error message + "Retry" button; pressing "Retry" calls the mocked `refetch`.
- **(2026-07-13 revision)** mocking it as `isSuccess: true` with an empty `styleKeywords` array: renders the empty-state message, not a blank chip row.
- mocking it as `isSuccess: true` with the 9 seeded style keywords: multiple chips can be `selected` simultaneously (multi-select, no cap per the ticket).
- wardrobe type: selecting one chip deselects any previously-selected one (single-select) — unaffected by the taxonomies query's state, since this list is still the static `WARDROBE_TYPES` constant.

`mobile/__tests__/features/onboarding/components/Step3OccasionPriorities.test.tsx`
- **(2026-07-13 revision)** loading/error/empty states as above, exercised for `occasionTypes`.
- all 9 chips render with the neutral (non-occasion-coloured) `Badge` style — asserts the BL-008 decision is actually implemented, not accidentally reverted to a patchy 4-coloured/5-neutral mix.
- selecting a 4th occasion when 3 are already selected does not add a 4th (asserts the store's cap, exercised through the component).

`mobile/__tests__/features/onboarding/components/Step4BudgetColours.test.tsx`
- budget: single-select across the 4 ranges — unaffected, still static.
- **(2026-07-13 revision)** loading/error/empty states as above, exercised for `colourPalette` (loading state asserts 12 `Skeleton variant="circle"` render, not `TaxonomyChipsSkeleton`).
- colours: selecting a 6th when 5 are already selected does not add a 6th; asserts the 4×3 grid renders all 12 swatches (from the mocked query data) without a horizontal scroll container.

`mobile/__tests__/app/(auth)/onboarding.test.tsx`
- brand-new user (`full_name` null, `onboarding_completed` false): renders Step 1 directly, no `ResumePrompt`.
- returning incomplete user (`full_name` non-null, `onboarding_completed` false): renders `ResumePrompt` first; "Continue Setup" advances the pager to Step 2, pre-filled from `fetchOnboardingProgress`.
- pressing "Skip" at any step calls `router.replace('/')` without calling `completeOnboarding`.
- reaching Step 4 and pressing "Get Started" calls `completeOnboarding` with the full assembled `StylePreferences` object, then `router.replace('/')`.
- `getItemType` returns 4 distinct values for the 4 fixed step items (regression guard for the recycling caveat above) — **(2026-07-13 revision)** this assertion is unaffected by the taxonomies revision (see the explicit "no change needed" confirmation in the FlashList pager section above); no new assertion needed here beyond the existing one.
- **(2026-07-13 revision)** mounting the wizard with `useOnboardingTaxonomiesQuery` mocked as still-loading does not crash the shell and Step 1 (which doesn't depend on the query) still renders/functions normally.

`mobile/__tests__/features/auth/auth.service.test.ts` (modified)
- `checkOnboardingCompleted`: mocks `supabase.from('users').select('onboarding_completed').eq().maybeSingle()`, asserts `true`/`false` mapping, and `false` on a thrown/failed query (fail-safe).

`mobile/__tests__/features/auth/auth.queries.test.tsx` (modified)
- `useOnboardingCompletedQuery`: same `enabled: false` assertion as before, renamed.

`mobile/__tests__/app/(auth)/verify-otp.test.tsx` (modified)
- same routing assertions as SS-003's design (`false → /onboarding`, `true → /`), updated to mock the renamed hook.

Manual/device verification (cannot be covered by any of the above):
- Actual horizontal-swipe paging feel (momentum/snap) on a real device — BL-013 (dev server unreachable from phone on same WiFi) still blocks this, same as it blocked SS-003/SS-008's device-level checks.
- Visual confirmation of the 4×3 colour grid and 9-chip occasion row on an actual 5-inch screen (can be approximated in an emulator/browser resize, not a real device, until BL-013 is resolved).
- **(2026-07-13 revision)** Actual DB round-trip verification that `003_onboarding_taxonomies.sql`'s seed rows are readable by an authenticated (non-service-role) client under the new RLS policies — the service-level unit tests above all mock the Supabase client, so this specific RLS-policy-actually-works check needs a real Supabase project/staging run, not just unit tests.

## Open questions / blockers

1. **"Can return to complete onboarding from Profile → Edit Preferences" cannot be closed end-to-end this ticket** — no Profile tab exists yet (`app/(tabs)` currently has only `_layout.tsx` and `index.tsx`; SS-005, "Home Screen Shell + Bottom Tab Navigation," is what builds the 5-tab bar including Profile, and SS-005 has not shipped). This design makes `/onboarding` re-enterable and pre-fillable (satisfying the *destination* side of the AC), but there is no actual button/screen yet to navigate *from*. Flagging as a cross-ticket dependency this ticket cannot fully close — logged to backlog (BL-023) rather than silently marking the AC done.
2. **Migration scope**: this design adds a DB trigger (`supabase/migrations/002_onboarding_completed.sql`) plus, as of this revision, three new reference tables (`003_onboarding_taxonomies.sql`) as part of a nominally frontend-wizard ticket. This is a deliberate call, not an oversight — BL-018 explicitly named this exact ticket as the one that needed to decide between a DB trigger and an application-level insert, and the ticket's own edge case (checking a persisted signal for "incomplete state") cannot function without one of the two existing; the taxonomies tables are likewise a direct, explicit requirement of the ticket's own (revised) Technical Notes, not scope creep. If review disagrees with schema migrations living in this ticket's scope, the fallback for `002` is an application-level upsert inside `hooks/useAuth.ts`; there is no realistic fallback for `003` other than a hardcoded union (i.e., reverting the very requirement that prompted this revision) — flagging this explicitly in case review wants the taxonomies tables split into their own ticket instead.
3. **BL-008 (occasion colours) remains open** — this ticket ships Step 3 with all-neutral chips rather than inventing 5 more occasion colours (see "Concrete values" above for the full reasoning). Needs a product/design decision before any ticket can occasion-colour-code these chips.
4. **New: no 12-swatch fashion colour palette exists** — this ticket ships a clearly-labeled placeholder `colour_palette` seed set (4 of 12 reusing already-approved brand hexes, 8 new placeholders) rather than inventing a final palette. Logged as BL-022; unaffected by this revision's storage-location change.
5. **BL-013 (dev server unreachable from phone on same WiFi)** still blocks any real-device verification of the pager's swipe/paging feel and the small-screen grid layout — same standing gap as SS-003/SS-008.
6. **FlashList-for-a-fixed-4-item-pager tradeoff** (see dedicated section above) — proceeding with FlashList per the ticket's explicit instruction, but flagging that its recycling machinery buys nothing here versus a plain `ScrollView horizontal pagingEnabled`, in case a future project-wide decision wants to revisit this specific case.
7. **(2026-07-13 revision) `occasion_types` table name vs. the existing `occasion_type` enum**: flagging explicitly for reviewer sign-off, per the instruction to double-check reasonable-sounding-but-worth-confirming design choices rather than silently proceeding. Postgres has no naming conflict between a `TYPE` and a `TABLE` (different object namespaces, and singular vs. plural besides), and the two serve genuinely different, already-documented purposes (wardrobe-tagging enum vs. onboarding-UI reference table) — but the names are close enough that a future developer skimming `\d occasion*` in `psql` or grepping the codebase could reasonably assume they're the same thing or should be kept in sync, when they are not and do not need to be. This design proceeds with `occasion_types` (matching the ticket's own Technical Note wording) rather than inventing a differently-named table (e.g. `onboarding_occasion_options`) that wasn't asked for — but this is exactly the kind of naming call worth a reviewer's explicit yes/no before the Developer phase, not an assumption locked in silently.
8. **(2026-07-13 revision) `staleTime`/`gcTime` values for `useOnboardingTaxonomiesQuery` (24h / `Infinity`) are an Architect judgment call**, not a value specified anywhere in the ticket or CLAUDE.md. If product/review wants a different cache-bust policy (e.g., shorter, to reflect newly-added occasions faster; or explicit invalidation tied to app foreground/relaunch rather than a fixed duration), that should be decided before or during the Developer phase rather than the Developer silently keeping or silently changing this Architect-chosen default.

## Backlog logging

Appended to `docs/BACKLOG.md`'s Open table (original Architect pass, unchanged by this revision):
- **BL-022**: No 12-swatch fashion colour palette defined anywhere in the design system for SS-004's Step 4 colour-preference multi-select; this ticket ships a placeholder (partially reusing approved brand hexes) pending a product/design decision. Still open; this revision only moved the placeholder's storage from a TS constant to a seeded DB table, which does not resolve the underlying product-sign-off gap.
- **BL-023**: SS-004's "resume onboarding from Profile → Edit Preferences" AC cannot be closed end-to-end because SS-005 (Home Screen Shell + Bottom Tab Navigation), which builds the Profile tab, has not shipped yet. SS-005's Architect/Developer must wire an "Edit Preferences" entry point that calls `router.push('/onboarding')`.

BL-018 (no `public.users` auto-provisioning / no `onboarding_completed` flag) is **moved to Resolved** — this ticket's migration (`002_onboarding_completed.sql`) adds both the trigger and the column, and `auth.service.ts`/`auth.queries.ts` are updated to check the new flag instead of row existence.

BL-008 (occasion colour coverage gap) remains **Open** — explicitly addressed (Step 3 ships with neutral chips, not colour-coded) but not resolved, per the reasoning above; not silently re-deferred.

BL-007 (no semantic error/danger colour) remains **Open** — reused as-is for the "Other" city validation error, same as SS-003's precedent, not resolved.

**No `docs/BACKLOG.md` changes were made during this 2026-07-13 revision pass** — per this pass's explicit instruction, that bookkeeping is handled directly by the orchestrating conversation, not by this design-doc revision. The open items surfaced by this revision (items 7 and 8 in "Open questions" above — the `occasion_types` naming collision and the Architect-chosen cache policy) are noted here and in "Open questions" for visibility but were intentionally not turned into new BL-XXX rows by this pass.
