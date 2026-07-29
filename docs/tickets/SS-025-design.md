# SS-025 — Occasion Taxonomy & Extensibility Migration — Design

Ticket: [`docs/tickets/raw/SS-025.md`](raw/SS-025.md) · Source proposal: [`docs/proposals/EXECUTION-PLAN.md`](../proposals/EXECUTION-PLAN.md) §3.1/§4 · Amendment: `AMEND-001`
Architect pass: 2026-07-28 (Opus, full lane)

**This document is the Developer's spec.** It is distilled from the execution plan and the raw ticket — do not re-open either. Every value below is fixed; where a value is my own judgement rather than pinned upstream, it says so inline.

---

## 1. Scope restatement

Occasions are currently a 12-value Postgres `ENUM` (`occasion_type`, `001_initial.sql:18`) mirrored into a closed TypeScript union (`wardrobe.types.ts`), a hardcoded array (`OCCASION_TYPES`), a partial colour map (`OCCASION_BADGE_COLOR_MAP`, 4 of 12), a Python `Literal` (`ai/ports/interfaces.py`), a hardcoded Gemini prompt vocabulary, and — separately and inconsistently — a 9-row `occasion_types` table used only by onboarding. This ticket collapses all of that into **one** data-driven registry: an `occasions` table (slug PK + metadata: hierarchy, kind, formality, region/culture scope, styling rules, date rule, tier gate, badge colour, active flag, sort order) plus an `occasion_aliases` normalisation table. The four columns that stored the enum (`wardrobe_items.occasion_tags`, `outfits.occasion`, `suggestion_sessions.occasion`, `social_posts.occasion`) become `TEXT[]`/`TEXT` slugs, the enum type is dropped, and the mobile app fetches its occasion vocabulary at runtime through the *existing* onboarding taxonomy service rather than importing constants. Adding an occasion becomes an `INSERT`. The trade — the compiler no longer enumerates valid occasions — is paid for with runtime normalisation and validation at every write boundary, in the application *and* in the database, and unknown AI-emitted slugs are captured rather than dropped or rejected.

This is Epic 3's foundation ticket: it precedes SS-020 and unblocks SS-030/SS-031. It ships against a **live remote project with real dev data** (`mefpfykuinasgkpfhmzk`: 1 user, 3 wardrobe items, 1 wear), so the migration is staged expand → migrate → contract with a captured before/after fixture.

---

## 2. Blast radius `[VERIFIED 2026-07-28 — ripgrep over the working tree, excluding node_modules]`

The raw ticket's counts are corrected here. Method: `Grep` for `occasion` (case-insensitive) across `mobile/` and `backend/`.

| Surface | Ticket claimed | Actual | Note |
|---|---|---|---|
| Forward migrations | 1 | **3 new** (`007`, `008`, `009`) | One file per expand/migrate/contract step — see §4. Still forward-only; `001_initial.sql` is never edited. |
| Backend source | 5 | **5 modified + 3 new** | Modified list below matches the plan exactly. |
| Backend tests | 6 | **5 modified + 2 new** | Only 5 backend test files reference occasions. |
| Mobile source | 30 | **32 reference it; 19 need edits, 13 are no-change** | Full split in §5.3. Includes `mobile/types/supabase.ts` (regenerate) and `tailwind.config.js` (no change). |
| Mobile tests | (not counted) | **31 reference it; ~14 need edits** | Enumerated in §7. |

Total files containing the string `occasion`: **63 mobile + 10 backend = 73**. The "30 mobile files" figure in the ticket counts source only and is close (32); it omits tests entirely.

---

## 3. Concrete values to use, not invent

### 3.1 `occasions` — column contract

```
key            TEXT PRIMARY KEY          CHECK (key ~ '^[a-z][a-z0-9_]*$')
parent_key     TEXT REFERENCES occasions(key) ON DELETE RESTRICT
                                         CHECK (parent_key IS DISTINCT FROM key)
label          TEXT NOT NULL
labels_i18n    JSONB NOT NULL DEFAULT '{}'::jsonb
kind           TEXT NOT NULL             CHECK (kind IN ('everyday','ceremony','festival','travel',
                                                         'sport','professional','social','milestone','religious'))
formality      SMALLINT NOT NULL         CHECK (formality BETWEEN 0 AND 10)
region_scope   TEXT[]                    CHECK (region_scope  IS NULL OR cardinality(region_scope)  > 0)
culture_scope  TEXT[]                    CHECK (culture_scope IS NULL OR cardinality(culture_scope) > 0)
styling_rules  JSONB NOT NULL DEFAULT '{}'::jsonb
date_rule      JSONB
tier_gate      TEXT NOT NULL DEFAULT 'free'  CHECK (tier_gate IN ('free','premium','atelier'))
badge_color    TEXT NOT NULL             CHECK (badge_color IN ('wedding','office','festival','casual'))
is_active      BOOLEAN NOT NULL DEFAULT true
sort_order     INTEGER NOT NULL DEFAULT 100
created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
```

Indexes: `idx_occasions_active_sort ON occasions (is_active, sort_order)`, `idx_occasions_parent ON occasions (parent_key)`. No GIN on `region_scope`/`culture_scope` — the table is 12 rows and will be low-hundreds at most; a sequential scan is correct here. Revisit only if profiling says otherwise.

**Null semantics — pin these, they are the #1 silent-failure mode in the raw ticket's edge cases:**
- `region_scope IS NULL` means **universal / pan-India**, *not* "no regions". Same for `culture_scope`.
- The empty array is **forbidden by CHECK**, precisely so nobody can write "applies nowhere" and get an occasion that silently never matches.
- The canonical applicability predicate — copy this verbatim wherever region/culture filtering is done (mobile selector, backend resolver, future SS-027/SS-030):
  ```sql
  (region_scope  IS NULL OR :user_region  = ANY(region_scope))
  AND (culture_scope IS NULL OR :user_culture = ANY(culture_scope))
  ```
  In TypeScript: `(o.regionScope === null || o.regionScope.includes(userRegion)) && (o.cultureScope === null || o.cultureScope.includes(userCulture))`. **Never** write `o.regionScope?.includes(r) ?? false` — that inverts the null meaning and every pan-India occasion disappears.

**`badge_color` is a design-token key, not a hex.** This is a deliberate departure from a literal reading of the execution plan's `badge_color TEXT -- closes BL-008 by construction`, and the reasoning is load-bearing: NativeWind class names are resolved at build time and CLAUDE.md forbids inline styles in JSX, so an arbitrary DB hex **cannot be rendered** without violating an anti-pattern rule. Constraining `badge_color` to the four occasion tokens SS-008 already ships (`wedding`/`office`/`festival`/`casual` → `bg-occasionWedding` etc.) means:
- `NOT NULL` + `CHECK` ⇒ every occasion has a colour by construction — `BL-008`'s patchy 4-coloured/8-neutral rendering cannot recur no matter how many occasions are added.
- `Badge`'s public API is **unchanged** — `badge_color`'s value set *is* `Badge`'s existing `OccasionKey` union. SS-008 regression surface stays near zero.
- Adding an occasion stays a pure `INSERT` (it picks an existing colour family). Only *widening the palette itself* needs a token change, which needs a design decision anyway — logged as `BL-088`.

### 3.2 Seed — the 12 existing enum keys, byte-identical

`sort_order` deliberately reproduces the enum's declaration order in `001_initial.sql:18-21`, which is also `OCCASION_TYPES`' order — so every shipped picker renders in exactly the order it does today. `labels_i18n` ships `'{}'` for all 12: **do not invent Hindi/regional labels** (see `BL-090`). `styling_rules` ships `'{}'` for all 12 — populating it is SS-027's job, not this ticket's. `region_scope`/`culture_scope`/`date_rule` ship `NULL` (universal) for all 12. `tier_gate` ships `'free'` for all 12. `parent_key` ships `NULL` for all 12 (all are top-level umbrellas). `is_active` ships `true` for all 12.

| key | label | kind | formality | badge_color | sort_order |
|---|---|---|---|---|---|
| `office` | Office | `professional` | 6 | `office` | 1 |
| `casual` | Casual | `everyday` | 2 | `casual` | 2 |
| `date_night` | Date Night | `social` | 6 | `wedding` | 3 |
| `wedding_guest` | Wedding Guest | `ceremony` | 9 | `wedding` | 4 |
| `festival` | Festival | `festival` | 7 | `festival` | 5 |
| `puja` | Puja | `religious` | 6 | `festival` | 6 |
| `party` | Party | `social` | 7 | `festival` | 7 |
| `travel` | Travel | `travel` | 3 | `casual` | 8 |
| `workout` | Workout | `sport` | 1 | `casual` | 9 |
| `beach` | Beach | `travel` | 2 | `casual` | 10 |
| `formal_event` | Formal Event | `ceremony` | 8 | `wedding` | 11 |
| `college` | College | `everyday` | 3 | `casual` | 12 |

`label`, `kind`, `formality` and `badge_color` assignments are **the Architect's call** (nothing upstream pins them). `formality` is an ordinal for SS-027's pre-filter and is tunable later with an `UPDATE`, no migration. Labels are the humanised enum keys, matching what `humanize()` in `wardrobe.constants.ts` produces today, except `wedding_guest` → "Wedding Guest" and `date_night` → "Date Night" which are already what the shipped UI shows via `humanize`.

### 3.3 `occasion_aliases` — seed

```
alias        TEXT PRIMARY KEY  CHECK (alias ~ '^[a-z][a-z0-9_]*$')
occasion_key TEXT NOT NULL REFERENCES occasions(key) ON DELETE CASCADE
created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
```

| alias | occasion_key | why |
|---|---|---|
| `wedding` | `wedding_guest` | **Required** — the shipped `occasion_types` onboarding table and `OCCASION_PILLS` both use `wedding`. Without this, existing user preference data and deep links break. |
| `date` | `date_night` | **Required** — same two sources. |
| `work` | `office` | plausible Gemini/user variant |
| `gym` | `workout` | plausible Gemini/user variant |
| `pooja` | `puja` | common transliteration |
| `vacation` | `travel` | plausible Gemini variant |
| `formal` | `formal_event` | plausible Gemini variant |
| `everyday` | `casual` | plausible Gemini variant |

The first two are **load-bearing data-migration mappings**, not conveniences. The other six are my judgement; adding or removing them later is an `INSERT`/`DELETE`.

`alias` and `occasions.key` must be disjoint. This is **not** enforced by a constraint (no cross-table CHECK in Postgres) — it is enforced by *resolution order* (canonical key wins before alias lookup, so a collision is inert) plus an explicit test (§7). Do not add a trigger for this.

### 3.4 `occasion_unknown_tags` — the "store and log" sink

```
slug           TEXT PRIMARY KEY
occurrences    INTEGER NOT NULL DEFAULT 1
first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
sample_source  TEXT          -- 'wardrobe_items' | 'outfits' | 'suggestion_sessions' | 'social_posts'
sample_user_id UUID
```

This is the durable half of the raw ticket's *"store it and log it for review rather than dropping the tag or failing the item write"*. A backend `logger.info` would only cover the Gemini path; this covers **every** writer, including the outfit/social-post paths that do not exist yet.

### 3.5 RLS — exact policies

Mirrors `003_onboarding_taxonomies.sql`'s established pattern verbatim.

```sql
ALTER TABLE occasions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE occasion_aliases      ENABLE ROW LEVEL SECURITY;
ALTER TABLE occasion_unknown_tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_occasions" ON occasions
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_occasion_aliases" ON occasion_aliases
  FOR SELECT USING (auth.role() = 'authenticated');
```

**Deliberately no INSERT/UPDATE/DELETE policy on any of the three, and no policy at all on `occasion_unknown_tags`.** With RLS enabled and no matching policy, writes from `anon`/`authenticated` are denied; `service_role` bypasses RLS. Absence of a policy *is* the write-protection mechanism — do not "fix" this by adding a permissive write policy.

`[trained-knowledge — service_role bypasses RLS via the `bypassrls` role attribute. Not asserted as verified: QA must prove it empirically per §7.4 — an `authenticated` INSERT into `occasions` must fail with a row-level-security error, and a `service_role` INSERT must succeed.]`

### 3.6 Normalisation contract (identical in SQL, Python and TypeScript)

Given a raw occasion string:
1. `trim` → `lower` → collapse runs of whitespace and `-` to a single `_` → strip any character outside `[a-z0-9_]`.
2. If the result matches `occasions.key` → **use it**.
3. Else if it matches `occasion_aliases.alias` → **use `occasion_key`**.
4. Else → **keep the normalised string as-is** and record it in `occasion_unknown_tags`. Never drop it. Never fail the write.

Then dedupe **preserving first-occurrence order** (order is not semantic for `occasion_tags`, but preserving it keeps the AC's byte-identical fixture assertion trivially true and avoids gratuitous diffs). Never sort.

Step 2 before step 3 is what makes an alias/key collision inert (§3.3).

---

## 4. Migration plan — expand → migrate → contract

Three files, applied in order. All three ship on the same branch and in the same PR; each carries a `-- ROLLBACK:` comment block so any single step can be reverted without unwinding the others. **`001_initial.sql` is never edited** (`BL-060`).

### `supabase/migrations/007_occasions_registry.sql` — EXPAND (purely additive)

1. `CREATE TABLE occasions`, `occasion_aliases`, `occasion_unknown_tags` per §3.1/§3.3/§3.4.
2. Indexes per §3.1.
3. RLS per §3.5.
4. Seed the 12 occasions (§3.2) and 8 aliases (§3.3).
5. Create the normalisation + logging functions:
   - `public.occasion_normalize_one(raw TEXT) RETURNS TEXT` — steps 1–3 of §3.6, returns the normalised string when unknown.
   - `public.occasion_is_known(slug TEXT) RETURNS BOOLEAN`.
   - `public.occasion_log_unknown(slug TEXT, src TEXT, uid UUID) RETURNS void` — `INSERT … ON CONFLICT (slug) DO UPDATE SET occurrences = occasion_unknown_tags.occurrences + 1, last_seen_at = now()`.
   - `public.occasion_normalize_array(raw TEXT[], src TEXT, uid UUID) RETURNS TEXT[]` — maps, logs unknowns, dedupes preserving order, returns `NULL` for `NULL` input and `'{}'` for empty input.

   All four are **`SECURITY DEFINER`** with **`SET search_path = public, pg_temp`**, so normalisation never depends on the caller's role or RLS visibility and the unknown-tag log is writable from a trigger without granting anyone table access. This is a privileged object: it takes only text/uuid arguments, executes no dynamic SQL, and writes exactly one table. Keep it that way.

Nothing reads these yet. Revert = `DROP TABLE`/`DROP FUNCTION`.

### `supabase/migrations/008_occasion_columns_to_text.sql` — MIGRATE

```sql
ALTER TABLE wardrobe_items       ALTER COLUMN occasion_tags TYPE TEXT[] USING occasion_tags::text[];
ALTER TABLE outfits              ALTER COLUMN occasion      TYPE TEXT   USING occasion::text;
ALTER TABLE suggestion_sessions  ALTER COLUMN occasion      TYPE TEXT   USING occasion::text;
ALTER TABLE social_posts         ALTER COLUMN occasion      TYPE TEXT   USING occasion::text;
```

Then attach the normalisation triggers (`BEFORE INSERT OR UPDATE`, `FOR EACH ROW`):
- `wardrobe_items` → `NEW.occasion_tags := public.occasion_normalize_array(NEW.occasion_tags, 'wardrobe_items', NEW.user_id);`
- `outfits`, `suggestion_sessions`, `social_posts` → scalar equivalent on `NEW.occasion`.

Then a guard block that **fails the migration** if the GIN index did not survive:
```sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND tablename='wardrobe_items'
                   AND indexname='idx_wardrobe_occasions' AND indexdef ILIKE '%using gin%') THEN
    RAISE EXCEPTION 'idx_wardrobe_occasions missing or no longer GIN after type change';
  END IF;
END $$;
```

`[inference, not verified — Postgres rebuilds indexes on a column whose type is altered, and `array_ops` is valid for both `occasion_type[]` and `text[]`, so `idx_wardrobe_occasions` should survive as a GIN index automatically. The DO block above converts that inference into a hard failure if it is wrong, and `backend/tests/test_db_schema.py::test_wardrobe_occasion_tags_gin_index_exists` already asserts it independently. If the guard fires, recreate the index explicitly rather than reverting the type change.]`

Old clients keep working across this step: PostgREST serialises both an enum and a text column as a JSON string, so a pre-migration mobile build reading `occasion_tags` sees an identical payload. `[inference — QA verifies empirically in §7.4 by reading a wardrobe item over REST before and after and diffing the JSON.]`

Revert = cast back with `USING occasion_tags::occasion_type[]` (valid while every stored value is still one of the 12) plus `DROP TRIGGER`.

### `supabase/migrations/009_drop_occasion_type_and_merge_taxonomy.sql` — CONTRACT

1. **Backfill `users.style_preferences.occasions_priority` through the alias map**, preserving order (this is what merges the onboarding vocabulary into the canonical one — `wedding` → `wedding_guest`, `date` → `date_night`):
   ```sql
   UPDATE users u
   SET style_preferences = jsonb_set(u.style_preferences, '{occasions_priority}', m.mapped, false)
   FROM (
     SELECT u2.id,
            jsonb_agg(COALESCE(a.occasion_key, e.value) ORDER BY e.ord) AS mapped
     FROM users u2
     CROSS JOIN LATERAL jsonb_array_elements_text(u2.style_preferences->'occasions_priority')
          WITH ORDINALITY AS e(value, ord)
     LEFT JOIN occasion_aliases a ON a.alias = e.value
     GROUP BY u2.id
   ) m
   WHERE u.id = m.id;
   ```
   Users with no `occasions_priority` key produce no lateral rows and are left untouched (`jsonb_set` with `create_missing = false`). **Capture the before-state of the single live user's `style_preferences` before running this** — see §7.1.
2. `DROP TYPE occasion_type;` — guarded:
   ```sql
   DO $$ BEGIN
     IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_type t ON t.oid=d.refobjid
                WHERE t.typname='occasion_type' AND d.deptype='n'
                  AND d.classid='pg_attribute'::regclass) THEN
       RAISE EXCEPTION 'occasion_type still has column dependencies — 008 did not complete';
     END IF;
   END $$;
   DROP TYPE occasion_type;
   ```
3. `DROP TABLE occasion_types;` — the 9-row onboarding table, now superseded. **Rollback block must contain the full `CREATE TABLE` + 9 seed rows + RLS policy transcribed verbatim from `003_onboarding_taxonomies.sql:26-31, 49, 54-55, 76-85`.**

Step 3 is the only genuinely destructive statement in the ticket. It is safe here because (a) its only consumer is `onboarding.taxonomies.service.ts`, changed in the same PR, and (b) its content is fully reconstructible from `003`. It is nonetheless listed as an explicit sign-off item in §9.

### Applying it

Per this repo's established practice (see `docs/worklog/SS-015.md` DevOps entry), the **Developer** applies migrations to the linked project with `supabase db push` during the Developer phase, so the PR's drift check compares an already-synced remote. That means these three migrations hit real dev data at Developer time, not at merge time. Consequently:

- **Capture the fixture first** (§7.1) — before `supabase db push`, not after.
- After the push, run `supabase db diff --linked` locally and confirm it is empty after the workflow's documented filter. If it is **not** empty (the new `SECURITY DEFINER` functions and triggers are new object classes for this repo and may produce ownership/`ALTER FUNCTION` noise), **report the exact diff output — do not edit `.github/workflows/supabase-migrations.yml`'s filter.** That filter has already false-positived once (`BL-060`); a second unreviewed loosening is how a real drift gets waved through.
- Regenerate `mobile/types/supabase.ts` immediately after the push.

---

## 5. Files to create/modify

### 5.1 Database

| Path | Action |
|---|---|
| `supabase/migrations/007_occasions_registry.sql` | **new** — §4 EXPAND |
| `supabase/migrations/008_occasion_columns_to_text.sql` | **new** — §4 MIGRATE |
| `supabase/migrations/009_drop_occasion_type_and_merge_taxonomy.sql` | **new** — §4 CONTRACT |

### 5.2 Backend (`backend/`)

| Path | Action |
|---|---|
| `ai/ports/interfaces.py` | **modify** — delete the `OccasionType` `Literal`; `GarmentTags.occasion_tags: list[str]` with a `mode="before"` validator that coerces to `list[str]`, trims/normalises shape only (no vocabulary check — that happens in the service, which has DB access). Update the class docstring: `occasion_tags` moves from *strict, out-of-vocabulary fails the payload* to *lenient-with-capture*, matching `pattern`/`fabric`'s existing posture and the raw ticket's edge case. Leave `IVisionProvider`/`IStylingProvider` **signatures untouched** (Open/Closed). |
| `adapters/interfaces.py` | **modify** — add `IOccasionRepository` ABC: `async def fetch_registry(jwt: str) -> OccasionRegistrySnapshot`. Update the `update_tagging_result` docstring's column list note. |
| `adapters/occasion_repository.py` | **new** — `SupabaseOccasionRepository`, following `wardrobe_repository.py`'s exact pattern: fresh `acreate_client` per call with `postgrest.auth(jwt)`, anon key, **never `service_role`**. Reads `occasions` (active only: key, label, badge_color, kind, parent_key, sort_order) and `occasion_aliases`. |
| `services/occasion_normalizer.py` | **new** — `OccasionNormalizer`: holds an `OccasionRegistrySnapshot` behind a **60-second TTL in-process cache**; implements §3.6 steps 1–3 plus order-preserving dedupe; returns `(normalized: list[str], unknown: list[str])` so the caller can log. On a registry fetch failure it **falls back to the last successful snapshot** and, if there is none, returns the input normalised-but-unmapped — tagging must never fail because the registry read failed. |
| `services/wardrobe_tagging_service.py` | **modify** — constructor takes `OccasionNormalizer`; `_write_success` normalises `tags.occasion_tags` before building `tag_columns`, and emits one `logger.warning("occasion_unknown", extra={"user_id", "item_id", "slug"})` per unknown slug. Unknown slugs are still written to the column. |
| `ai/adapters/gemini_vision_adapter.py` | **modify** — `_TAXONOMY_PROMPT` becomes a template; the hardcoded `[office, casual, date_night, …]` list (line ~96) is replaced by `{occasion_vocabulary}` rendered at call time from the registry snapshot (`key` list, comma-joined, in `sort_order`). The adapter takes the normaliser/registry via **constructor injection** — `tag_garment(image_bytes)`'s signature does not change. **This is what makes the AC's "insert `ganesh_chaturthi`, no rebuild" demo actually reach the AI**, not just the pickers. |
| `ai/adapters/mock_styling_adapter.py` | **modify** — its 7 hardcoded fixture `occasion` values are all canonical keys already; only the type annotations/comments referencing `OccasionType` change. Verify no behavioural change. |
| `dependencies/` (wiring) | **modify** — provide `IOccasionRepository`/`OccasionNormalizer` via `Depends()` wherever `WardrobeTaggingService`/`GeminiVisionAdapter` are constructed. Routers depend on the port, never the adapter. |

### 5.3 Mobile (`mobile/`)

**Needs edits (19):**

| Path | Action |
|---|---|
| `features/onboarding/onboarding.taxonomies.service.ts` | **modify (heavy)** — replace the `occasion_types` query with `occasions` (`key,label,badge_color,kind,parent_key,sort_order` where `is_active`, ordered by `sort_order`) and add an `occasion_aliases` query. Four parallel queries instead of three, same all-or-nothing error posture. On success, write the whole payload through to `lib/storage.ts`; on failure, read it back (see §6.5). This is the single taxonomy fetcher — **do not add a second one.** |
| `features/onboarding/onboarding.occasions.ts` | **new** — pure, I/O-free helpers over a fetched snapshot: `normalizeOccasionSlug`, `resolveOccasionKey`, `occasionLabel(slug)` (registry label → `humanize(slug)` fallback), `occasionBadgeColor(slug)` (registry `badge_color` → `undefined`/neutral fallback if the value isn't one of `Badge`'s four `OccasionKey`s), `topLevelOccasions`, `activeOccasionsPlus(currentTags)`. Unit-testable without mocks. |
| `features/onboarding/onboarding.types.ts` | **modify** — `OccasionOption extends TaxonomyOption { badgeColor: OccasionKey; kind: string; parentKey: string \| null }`; `OccasionAlias { alias: string; occasionKey: string }`; `OnboardingTaxonomies` drops `occasionTypes`, gains `occasions: OccasionOption[]` and `occasionAliases: OccasionAlias[]`. `OccasionPriorityKey` stays `string`. |
| `features/onboarding/onboarding.queries.ts` | **modify** — `useOnboardingTaxonomiesQuery` keeps its key/staleTime/gcTime/`enabled: Boolean(session)` gate **exactly as-is** (that gate is load-bearing — see the comment at line 167; an unauthenticated read returns empty-but-successful and poisons the cache). Add `useOccasionTaxonomy()` returning `{ occasions, topLevelOccasions, resolveOccasion, label, badgeColor, isLoading, isError, isStale }`. |
| `features/onboarding/components/Step3OccasionPriorities.tsx` | **modify** — source `topLevelOccasions` (12, was 9); pass `occasion={badgeColor(key)}` to `Badge` (was neutral for all). Max-3 cap unchanged. |
| `features/onboarding/components/EditOccasionPrioritiesSection.tsx` | **modify** — same two changes. |
| `features/wardrobe/wardrobe.types.ts` | **modify (heavy)** — delete the 12-member `OccasionType` union; add `export type OccasionSlug = string;`. Update `GarmentTagsDraft.occasionTags`, `WardrobeItemRealtimeRow.occasion_tags`, `WardrobeFilterState.occasionFilter` to `OccasionSlug`. Do **not** keep an `OccasionType` alias — let the compiler find all 10 call sites. |
| `features/wardrobe/wardrobe.constants.ts` | **modify** — delete `OCCASION_TYPES` (lines 104-117) and `OCCASION_BADGE_COLOR_MAP` (lines 133-142), and the `OccasionType` import. |
| `features/wardrobe/wardrobe.store.ts` | **modify** — `setOccasionFilter: (value: OccasionSlug \| 'all')`. |
| `features/wardrobe/wardrobe.selectors.ts` | **modify** — no logic change (`includes` on strings still works); type only. **Do not** filter out inactive occasions here — an applied filter on a since-deactivated occasion must keep working. |
| `features/wardrobe/wardrobe.service.ts` | **modify** — normalise + dedupe occasion slugs on every write path before the Supabase call (`saveWardrobeItemTags` and the Review-step save), using `onboarding.occasions.ts`'s helpers seeded from the cached snapshot. The DB trigger is the backstop, not the primary. |
| `features/wardrobe/wardrobe.queries.ts` | **modify** — re-export a thin `useOccasionOptions()` wrapper over `useOccasionTaxonomy()` so wardrobe components don't import from `features/onboarding/` directly at the component layer. (Cross-domain hook import at the queries layer only — logged as `BL-089`.) |
| `features/wardrobe/components/WardrobeFilterSheet.tsx` | **modify (medium)** — occasion chips come from `useOccasionOptions()`; `label={label(key)}` (a real label instead of today's raw slug); `occasion={badgeColor(key)}`. Add loading (reuse `TaxonomyChipsSkeleton`) and error states for the occasion section only — the other three sections must still work if the taxonomy fetch failed. |
| `features/wardrobe/components/ReviewStep.tsx` | **modify (medium)** — options = `activeOccasionsPlus(draft.occasionTags)`: the active registry **union** any slug already on the draft. Without this union an unknown Gemini slug or a deactivated occasion is invisible in the picker and gets silently dropped on save. Chips for out-of-registry tags render selected, with `humanize(slug)` and neutral colour. |
| `features/wardrobe/components/EditItemTagsForm.tsx` | **modify (medium)** — identical union treatment. |
| `features/wardrobe/components/ItemDetailSheet.tsx` | **modify** — `label={label(occasion)}`, `occasion={badgeColor(occasion)}`; must still render a label for a deactivated **or** unknown slug (`humanize` fallback). |
| `features/home/home.constants.ts` | **modify** — `OCCASION_PILLS` keys become canonical slugs: `wedding` → `wedding_guest`, `date` → `date_night`. Emoji, labels, order and the 6-item curation stay exactly as SS-005 pinned them (the pill list stays hardcoded — it is a curated subset with emoji, and emoji are not in the registry). Replace the BL-008 comment block with the new rationale. |
| `features/home/components/OccasionPillRow.tsx` | **modify** — pass `occasion={badgeColor(pill.key)}` (pills gain colour; previously all neutral by the BL-008 workaround). Neutral while the taxonomy query is loading — never block the home screen on it. |
| `app/(tabs)/style.tsx` | **modify** — run the incoming `occasion` query param through `resolveOccasionKey` before matching `OCCASION_PILLS`, so a deep link carrying the old `wedding`/`date` keys still resolves. |
| `lib/storage.ts` | **new** — the `AsyncStorage` last-known-good taxonomy cache (§6.5). This is the `storage.ts` slot CLAUDE.md's folder structure already reserves in `lib/`. |
| `types/supabase.ts` | **regenerate** — `Enums.occasion_type` disappears; the four columns become `string[] \| null` / `string \| null`; `occasions`/`occasion_aliases`/`occasion_unknown_tags` Row/Insert/Update types appear; `occasion_types` disappears. Never hand-edit. |

**Reference occasions but expected to need no change (13)** — verify with `tsc`, don't pre-emptively edit: `components/ui/Badge.tsx`, `components/ui/tokens.ts`, `components/ui/index.ts`, `tailwind.config.js`, `app/dev-ui-kit.tsx`, `app/(tabs)/wardrobe.tsx`, `app/(auth)/onboarding.tsx`, `app/edit-preferences.tsx`, `app/wardrobe/upload.tsx`, `features/home/home.types.ts`, `features/onboarding/onboarding.store.ts`, `features/onboarding/onboarding.service.ts`, `features/onboarding/components/TaxonomyChipsSkeleton.tsx`.

`Badge.tsx` and `tokens.ts` being untouched is the point of §3.1's token-key decision — SS-008's shipped API and hexes are not disturbed.

---

## 6. Behavioural specs

### 6.1 What "one vocabulary" means for onboarding

Onboarding Step 3 and the Edit-Preferences occasion section source **top-level active occasions** (`parent_key IS NULL AND is_active`), ordered by `sort_order` — **12 today, up from the current 9.** The 9 old onboarding keys all map into the 12 (7 identical, 2 via alias). Users gain `workout`, `beach`, `formal_event` as selectable priorities; nobody loses an option.

`parent_key IS NULL` is also what stops the registry's growth from flooding onboarding: when `ganesh_chaturthi` is inserted with `parent_key = 'festival'`, it appears in wardrobe tagging, filters and AI vocabulary, and correctly does **not** appear in the onboarding priorities wizard or the home pill row. This uses only columns the execution plan already specifies — no new "surfaces" column. **Convention: seed new specific occasions with a `parent_key`; reserve `parent_key IS NULL` for genuine top-level umbrellas.** Depth beyond two levels is not prevented and not used.

This is a visible change to a shipped ticket's UI (SS-004) — flagged for sign-off in §9.

### 6.2 Deactivated occasion (`is_active = false`)

- Items **keep** the tag — nothing rewrites `occasion_tags` on deactivation.
- Pickers/filters **hide** it (registry query filters `is_active`), **except** it still renders (selected) in Review/Edit if the item currently carries it (§5.3's union rule), so editing an item never silently strips it.
- `ItemDetailSheet` **still renders the label** — the registry row still exists, only `is_active` is false. The mobile snapshot only fetches active rows, so an inactive slug falls through to `humanize(slug)`. That is acceptable and required behaviour (never a blank chip), but note the label degrades from "Wedding Guest" to "Wedding Guest" only by coincidence of the humaniser. **If a nicer label matters, fetch inactive rows too and filter for display only** — see §9 open question 4.
- An applied filter on a since-deactivated occasion keeps filtering (§5.3, `wardrobe.selectors.ts`).

### 6.3 Unknown AI slug — end-to-end

Gemini returns `"ganesh_chaturthi"` (or `"Ganesh Chaturthi"`, or `"sangeet"`):
1. `GarmentTags` accepts it (no `Literal` any more) — the payload does **not** fail validation.
2. `OccasionNormalizer` normalises shape, finds no key and no alias → returns it in `unknown`.
3. `WardrobeTaggingService` writes it to `occasion_tags` anyway and logs `occasion_unknown`.
4. The DB trigger re-normalises (idempotent — already canonical shape), finds it unknown, and upserts `occasion_unknown_tags`.
5. Mobile Review shows it as a selected chip (union rule), `humanize`d, neutral colour. The user can keep or remove it.
6. Product later reviews `occasion_unknown_tags` and either inserts a real `occasions` row (the tag becomes first-class retroactively, on every item already carrying it) or inserts an `occasion_aliases` row (existing items are normalised on their next write).

**Nothing in this path drops the tag or fails the item write.** That is the non-negotiable property.

### 6.4 Write boundaries — the `BL-078` checklist

| # | Boundary | Where validation lives | Status after this ticket |
|---|---|---|---|
| 1 | Gemini tagging output | `OccasionNormalizer` in `wardrobe_tagging_service._write_success` + DB trigger | **built** |
| 2 | Upload Review step save | `wardrobe.service.ts` normalise-on-write + DB trigger | **built** |
| 3 | Item edit (`EditItemTagsForm`) | same | **built** |
| 4 | Outfit save (`outfits.occasion`) | DB trigger only — **no application write path exists yet** (0 rows, no code) | **DB-covered; app-layer lands with SS-020/SS-023** |
| 5 | Social post (`social_posts.occasion`) | DB trigger only — no write path exists yet (Epic 4) | **DB-covered; app-layer lands with Epic 4** |
| 6 | Suggestion session (`suggestion_sessions.occasion`) | DB trigger only — no write path yet | **DB-covered; app-layer lands with SS-020** |

The DB trigger is what lets rows 4–6 be honestly called covered today. `BL-078` stays **Active** as a standing obligation for every *new* occasion write path.

### 6.5 Last-known-good taxonomy cache

`useOnboardingTaxonomiesQuery` is in-memory (`gcTime: Infinity`) and therefore empty on every cold start. Add persistence:

- On every successful fetch, `lib/storage.ts` writes `{ version: 1, fetchedAt: <ISO>, payload }` to `AsyncStorage` under `stylesense.taxonomies.v1`.
- `fetchOnboardingTaxonomies()` on network/RLS error: read the cached payload; if present, return it and mark `isStale: true`; if absent, rethrow.
- Consumers render: fresh → normal; stale → normal (optionally a subtle indicator, not required by any AC); no cache and error → the component's **error + retry** state, which every one of these components must have per CLAUDE.md.

The "no cache and offline on first ever launch" case renders an error/retry state, **not** an empty chip row — that satisfies *"never render an empty occasion picker"* without reintroducing a bundled hardcoded vocabulary, which would contradict the AC that removes `OCCASION_TYPES`. Flagged as open question 3 in case the user prefers a bundled emergency floor.

`[trained-knowledge — `@react-native-async-storage/async-storage@2.2.0` (already a dependency) ships a web implementation backed by `localStorage`. Developer must confirm on `npx expo start --web`, since this app is web-first; if it does not work on web, fall back to `localStorage` directly behind the same `lib/storage.ts` interface.]`

### 6.6 Concurrency posture (`BL-066` / `BL-036`)

No new read-then-write is introduced. `occasion_tags` is written as a whole-column value from a user-edited draft (last-write-wins, as today), and the trigger's normalisation happens inside the same statement — it does not read-then-write a second row. The `occasion_unknown_tags` upsert is a single `INSERT … ON CONFLICT DO UPDATE`, atomic. **This ticket does not add a third instance of that class of bug**, and does not attempt to fix the two existing ones.

---

## 7. Test plan

### 7.1 Data fixture — do this first, before `supabase db push`

Capture and commit into `docs/worklog/SS-025.md` (the exact JSON, not a summary):
```sql
SELECT id, occasion_tags FROM wardrobe_items ORDER BY id;
SELECT id, style_preferences->'occasions_priority' FROM users ORDER BY id;
```
Expected content per the ticket's Status note: 3 rows whose tags draw from `casual, office, date_night, travel, formal_event, college, wedding_guest, festival, puja`. Re-run **after** all three migrations and assert `occasion_tags` is byte-identical per `id` (same values, same order). The `occasions_priority` comparison is a *mapped* comparison (`wedding`→`wedding_guest`, `date`→`date_night`), not identity — record both states.

### 7.2 Backend — `backend/tests/`

| File | Test |
|---|---|
| `test_occasion_normalizer.py` **(new)** | canonical key passes through unchanged |
| | alias `wedding` maps to `wedding_guest`; `date` → `date_night` |
| | `"  Wedding Guest "` normalises to `wedding_guest` (trim/lower/space→underscore) |
| | unknown slug is returned **in the output list** and reported in `unknown`, not dropped |
| | duplicate slugs dedupe preserving first-occurrence order; ordering is never sorted |
| | empty list → empty list; `None` → `None`; no exception on either |
| | a registry fetch failure falls back to the last snapshot; with no snapshot, input is returned normalised-but-unmapped and no exception escapes |
| | key/alias collision: canonical key wins (resolution order) |
| `test_occasion_repository.py` **(new)** | builds its client with the anon key + caller JWT, never `service_role` (mirrors `test_wardrobe_repository.py`'s existing assertion style) |
| | only `is_active = true` rows are requested |
| `test_ai_ports.py` **(modify)** | `GarmentTags` accepts an out-of-registry `occasion_tags` value without raising (the inverse of today's assertion) |
| | `season_tags` leniency is unchanged; `category` strictness is unchanged |
| `test_gemini_vision_adapter.py` **(modify)** | the rendered prompt contains every active registry key, sourced from the injected registry — assert a **newly inserted** fake key appears in the prompt (this is the "no rebuild" property at the AI layer) |
| | a response containing an unknown occasion string yields `success=True` with the tag retained |
| `test_wardrobe_tagging_service.py` **(modify/new)** | `_write_success` writes normalised tags to `tag_columns['occasion_tags']` |
| | an unknown slug is still written **and** emits exactly one `occasion_unknown` log record carrying `user_id`/`item_id`/`slug` |
| `test_mock_styling_adapter.py` **(modify)** | fixture occasion values still equal the canonical keys (no behavioural drift) |
| `test_db_schema.py` **(modify)** | `occasion_type` no longer exists in `pg_type` |
| | `occasions` has exactly 12 rows; the key set equals the 12 canonical keys |
| | every `occasions` row has a non-null `badge_color` in the 4-value set (**this is the `BL-008` structural assertion**) |
| | `idx_wardrobe_occasions` still exists and is still `USING gin` |
| | `wardrobe_items.occasion_tags` `data_type` is `ARRAY` of `text` |
| | RLS is enabled on `occasions`/`occasion_aliases`/`occasion_unknown_tags` |
| | `occasions.key` and `occasion_aliases.alias` sets are disjoint |
| | inserting `region_scope = '{}'` is rejected by CHECK |

### 7.3 Mobile — `mobile/__tests__/`

| File | Test |
|---|---|
| `features/onboarding/onboarding.occasions.test.ts` **(new)** | `normalizeOccasionSlug` matches the backend contract case-for-case (same table as §7.2 row 1-5) |
| | `occasionLabel` returns the registry label; falls back to `humanize(slug)` for an unknown slug |
| | `occasionBadgeColor` returns the registry token; returns `undefined` (neutral) for a slug not in the snapshot **and** for a `badge_color` value outside `Badge`'s four keys |
| | `topLevelOccasions` excludes rows with a `parentKey` |
| | `activeOccasionsPlus(['ganesh_chaturthi'])` includes the unknown slug exactly once, at the end |
| | region/culture predicate: `regionScope === null` matches every user region (the null-means-universal guard) |
| `features/onboarding/onboarding.taxonomies.service.test.ts` **(modify)** | queries `occasions` and `occasion_aliases`, not `occasion_types` |
| | requests only `is_active` rows, ordered by `sort_order` |
| | a successful fetch writes the payload to `lib/storage.ts` |
| | a failed fetch with a cached payload resolves with the cached payload and `isStale` |
| | a failed fetch with **no** cache rejects (so the hook's `isError` path renders) |
| `lib/storage.test.ts` **(new)** | round-trips a payload; a version mismatch is treated as a cache miss; corrupt JSON is treated as a cache miss and never throws |
| `types/supabase-types.test.ts` **(modify)** | delete the `occasion_type` describe block; keep `wardrobe_category` (21) and `plan_tier` (3). Add: `Constants.public.Enums` has no `occasion_type` key — the drift guard now guards its *absence*. |
| `features/wardrobe/components/WardrobeFilterSheet.test.tsx` **(modify)** | occasion chips render from the mocked taxonomy, with registry labels not raw slugs |
| | a newly-added mock occasion appears with no code change |
| | multi-select/apply/clear behaviour unchanged (SS-014 regression) |
| | taxonomy loading → skeleton; taxonomy error → error state, while season/colour/sort sections still work |
| `features/wardrobe/components/ReviewStep.test.tsx` **(modify)** | an unknown slug on the draft renders as a **selected** chip and survives a save round-trip |
| | a deactivated occasion already on the draft renders selected |
| `features/wardrobe/components/EditItemTagsForm.test.tsx` **(modify)** | add/remove/persist unchanged (SS-015 regression) with the fetched vocabulary |
| | an unknown tag is not dropped by an unrelated edit |
| `features/wardrobe/components/ItemDetailSheet.test.tsx` **(modify)** | renders a label for an unknown slug (humanised, neutral badge) |
| `features/wardrobe/wardrobe.service.test.ts` **(modify)** | occasion slugs are normalised + deduped before the Supabase write |
| `features/wardrobe/wardrobe.selectors.test.ts` **(modify)** | filtering by a slug not in the registry still matches items carrying it |
| `features/home/components/OccasionPillRow.test.tsx` **(modify)** | 6 pills, canonical keys, correct emoji/order (SS-005 regression) |
| | each pill carries a badge colour once the taxonomy resolves; neutral while loading |
| `features/onboarding/components/Step3OccasionPriorities.test.tsx` **(modify)** | renders the fetched top-level occasions; max-3 cap and skip behaviour unchanged (SS-004 regression) |
| `features/onboarding/components/EditOccasionPrioritiesSection.test.tsx` **(modify)** | same |
| `components/ui/Badge.test.tsx` **(modify)** | add a case per `badge_color` value asserting the right `bg-occasion*` class — **all four, driven from the registry's value set** (SS-008 regression + `BL-008` proof) |
| `app/(tabs)/style.test.tsx` **(modify)** | a deep link with the legacy `?occasion=wedding` still resolves to the Wedding pill |

### 7.4 Manual / live verification (cannot be unit-tested — QA must actually run these)

1. **Fixture equality** — §7.1, before and after. Byte-identical `occasion_tags` for all 3 items.
2. **RLS write-protection** — with an `authenticated` JWT, `INSERT INTO occasions …` must fail with a row-level-security error; the same insert with the `service_role` key must succeed. Both directions, observed, not assumed.
3. **The extensibility demo (the ticket's headline AC)** — `INSERT INTO occasions (key, parent_key, label, kind, formality, badge_color, sort_order) VALUES ('ganesh_chaturthi', 'festival', 'Ganesh Chaturthi', 'festival', 7, 'festival', 20);` then, **without rebuilding or restarting the app**, confirm: it appears in the wardrobe filter sheet and Review/Edit pickers with the right label and colour; it does **not** appear in onboarding Step 3 (it has a parent); it appears in the Gemini prompt vocabulary on the next tagging call. Then `UPDATE occasions SET is_active = false` and confirm §6.2's behaviour on an item already tagged with it.
4. **Wire-format compatibility** — read one wardrobe item over PostgREST before 008 and after 008; the JSON must be identical.
5. **Cold-start cache** — load the app authenticated (populates the cache), kill it, go offline, relaunch: occasion pickers render from cache, not empty. Then clear storage, stay offline, relaunch: pickers render an error/retry state, not an empty chip row.
6. **Drift check** — `supabase db diff --linked` empty after push (§4).

### 7.5 Mandatory regression scope — the 7 shipped tickets

QA executes this list directly; "the tests pass" is not a substitute for the manual column.

| Ticket | Re-verify — specifics |
|---|---|
| **SS-004** | Onboarding Step 3 renders **12** top-level occasions (was 9), in `sort_order`, each with a badge colour. Select 3 → 4th is blocked. Save → `users.style_preferences.occasions_priority` holds canonical slugs. Skip Step 3 → still completes. Re-enter the wizard → previously-saved priorities are still selected (this is the alias-backfill working; a user whose stored value was `wedding` must show "Wedding Guest" selected, not blank). Edit-Preferences section: same checks. |
| **SS-005** | Home pill row shows the same 6 pills, same emoji, same order. Each now carries a colour. Tapping each navigates to `/style?occasion=<canonical slug>` and the Style screen shows "<Label> looks — coming soon". A legacy link `?occasion=wedding` still resolves. Pills render (neutral) before the taxonomy query resolves — home never blocks or flashes empty. |
| **SS-008** | `Badge` occasion variants across **all 12 occasions**, not just 4: every occasion chip in Review, Edit, Filter, ItemDetail and Home renders with one of the four `bg-occasion*` classes and **none renders neutral** (the `BL-008` symptom). Label truncation at 20 chars still applies (check "Ganesh Chaturthi" and a longer synthetic label). `selected` border state unchanged. dev-ui-kit still renders. |
| **SS-012** | Tag a real photo end-to-end: the prompt sent to Gemini contains the registry vocabulary; returned tags land on the item; confidence/moderation/`ai_tags.tagging` behaviour unchanged. Force an unknown occasion (stub the adapter response) → item write succeeds, tag retained, `occasion_unknown` logged, row present in `occasion_unknown_tags`. Force a malformed occasion (`"Wedding Guest!!"`) → normalises to `wedding_guest`. |
| **SS-013** | Upload Review step: occasion chips render with labels (not raw slugs) and colours; AI-suggested tags arrive pre-selected; toggling works; save persists exactly the selected set; the low-confidence/disambiguation paths are unchanged. Batch upload of 2+ items still works. |
| **SS-014** | Catalogue occasion filter: open sheet → occasion section lists active occasions; select → grid filters; the selected-summary chip shows the **label**; Clear resets; a filter matching nothing shows the empty state (`NO_ITEMS_IN_CATEGORY_*`); combined occasion+season+colour+sort still composes; column-count breakpoints unaffected. |
| **SS-015** | Item edit: add an occasion, remove one, save, reopen — persisted exactly. Editing an item that carries an unknown/deactivated tag must not drop that tag. Delete + Mark Worn paths untouched (confirm `wardrobe_item_wears` trigger and `cost_per_wear` are unaffected by the type change — they share the `wardrobe_items` table that 008 rewrites). |

**Note for SS-015 specifically:** `ALTER COLUMN … TYPE` on `wardrobe_items` rewrites the table. `cost_per_wear` is a `GENERATED … STORED` column and `wardrobe_item_wears` has a composite FK to `wardrobe_items (id, user_id)`. Neither should be affected, but both must be re-verified post-migration rather than assumed — that is exactly the kind of adjacency a table rewrite can disturb.

---

## 8. Edge cases

Carried forward from the ticket, plus what the current codebase adds:

1. **Compile-time exhaustiveness is lost.** Mitigated by §6.4's six-boundary matrix, the DB trigger, and §7's tests. `BL-078` stays Active as a standing obligation.
2. **Gemini emits an unmodelled occasion** → §6.3. Never dropped, never fails the write.
3. **Occasion deactivated while items reference it** → §6.2.
4. **`region_scope`/`culture_scope` NULL = universal** → §3.1's pinned predicate + the `cardinality > 0` CHECK that makes "applies nowhere" unrepresentable.
5. **Taxonomy fetch fails on cold start** → §6.5.
6. **Two occasions with the same `label`** (regional new-year names) — `key` is identity, `label` is display-only. No unique constraint on `label`; do not add one. React keys must use `key`, never `label`.
7. **(new) The onboarding vocabulary and the enum vocabulary disagree on two keys** — `wedding`/`wedding_guest` and `date`/`date_night`. Live user preference data uses the *old* keys. Handled by the 009 backfill + permanent alias rows. Missing this would silently blank a user's saved onboarding priorities.
8. **(new) A tag on an item that is not in the fetched (active) registry is invisible in the pickers and gets dropped on the next save.** This is the sharpest regression risk in the whole ticket — today `OCCASION_TYPES.map` is the only chip source in Review/Edit. Fixed by the union rule in §5.3; tested in §7.3.
9. **(new) `WardrobeFilterSheet` currently labels chips with the raw slug** (`label={occasion}`). Once occasions can be arbitrary, showing `ganesh_chaturthi` to a user is not acceptable — labels now come from the registry.
10. **(new) `Badge` truncates labels at 20 characters.** Registry labels are unbounded. "Ganesh Chaturthi" fits (16); "Karwa Chauth Celebration" (24) would truncate. Not a bug, but seed labels should stay ≤ 20 chars where possible.
11. **(new) Alias/key collision** — inert by resolution order (§3.3), asserted by test.
12. **(new) The generated `mobile/types/supabase.ts` loses `Enums.occasion_type`.** `supabase-types.test.ts` currently asserts it has exactly 12 members and will fail loudly — that failure is *expected* and the test must be rewritten to assert absence, not deleted.
13. **(new) The drift check runs against a project the Developer already pushed to.** If the Developer forgets `supabase db push`, the PR's drift check fails with what looks like drift but is actually pending migrations. Documented in §4 so it is diagnosed correctly rather than by loosening the filter (`BL-060`).
14. **(new) `occasion_unknown_tags` can accumulate junk** from a misbehaving model (one row per distinct malformed string). Bounded in practice by normalisation collapsing case/whitespace variants; no cap is imposed. If it grows pathologically, that is itself the signal the table exists to surface.

---

## 9. Open questions / blockers — need sign-off before Developer starts

This is a full-lane ticket; these are the human-gate items.

1. **Onboarding Step 3 grows from 9 to 12 options** (§6.1) — `workout`, `beach`, `formal_event` become selectable priorities, and `Wedding` becomes `Wedding Guest`, `Date` becomes `Date Night`. This is a visible change to SS-004's shipped UI and is the direct consequence of merging the two vocabularies. **Recommended: accept.** The alternative (curating the onboarding subset) needs a column the approved plan doesn't have.
2. **`009` drops the `occasion_types` table.** It is the only genuinely destructive statement in the ticket, against a live (dev) project. Fully reconstructible from `003_onboarding_taxonomies.sql` and included in the rollback block. **Recommended: proceed.** The alternative is leaving a dead table that will regrow a second vocabulary.
3. **No bundled fallback vocabulary** (§6.5). First-ever launch, offline, no cache → error/retry state rather than an empty picker. A bundled 12-item seed constant would remove even that case, but reintroduces exactly the hardcoded constant the AC deletes. **Recommended: no bundled fallback.** Reverse if you'd rather never show an error there.
4. **Inactive occasions are not fetched by mobile**, so a deactivated tag's chip label degrades to the humanised slug (§6.2). Fetching all rows and filtering client-side would keep perfect labels at the cost of shipping retired vocabulary to the client. **Recommended: keep fetching active-only** — the humanised fallback is already required for genuinely unknown slugs, so this adds no new code path.
5. **`formality` values (§3.2) are my judgement**, not pinned by any source. They feed SS-027's pre-filter. If you have a view on the ordinal scale, now is cheaper than after SS-027 tunes against it — though changing them later is an `UPDATE`, not a migration.
6. **`badge_color` is a token key, not a hex** (§3.1). This is a deliberate, reasoned deviation from a literal reading of the execution plan's column comment. If you intended free hexes, say so — it requires either an inline-style exemption from CLAUDE.md or a NativeWind-safelist approach, both of which are more design surface than this ticket has.

**Not blockers, but the Developer must know:**
- The Developer applies these migrations to the **live** `mefpfykuinasgkpfhmzk` project during the Developer phase (§4). §7.1's fixture capture happens **before** that, and is a hard precondition, not a formality.
- `BL-060` is live risk on this ticket. Do not touch the CI filter; report the diff.
- `BL-079`/`BL-064` (`pattern`/`fabric`) are **explicitly out of scope**. The registry shape landed here — slug PK + label + `is_active` + `sort_order` + alias table + `SECURITY DEFINER` normalisation function + trigger — is directly reusable for them: a `patterns`/`fabrics` pair of tables plus `pattern_aliases`/`fabric_aliases` and the same trigger shape, with `badge_color` swapped for whatever display attribute those need. `BL-079` is updated to record that the precedent now exists; do not widen this ticket.

---

## 10. Backlog deltas

- **`BL-008` (tokens) → Resolved by SS-025 / Architect.** `badge_color` is `NOT NULL` with a `CHECK` against the four SS-008 occasion tokens, so no occasion can exist without a colour and the 4-of-12 patchy rendering cannot recur. Deferred by four prior Architect passes (SS-004, SS-005, SS-013, SS-014); dissolved rather than deferred a fifth time — it was never a "we need 8 more hexes" problem.
- **`BL-078` (schema) → stays Active, note updated** with §6.4's six-boundary matrix and the DB-trigger backstop that covers the three write paths that don't exist yet.
- **`BL-079` (schema) → stays Active, note updated** — the reusable registry shape is now concrete and named.
- **`BL-088` (tokens) → new, Active** — occasion badge palette is four semantic families; whether product wants more distinct colours as the registry grows.
- **`BL-089` (infra) → new, Active** — the single taxonomy fetcher now serves the whole app but lives under `features/onboarding/`; candidate for a `features/taxonomy/` domain.
- **`BL-090` (infra) → new, Active** — `occasions.labels_i18n` ships empty for all 12; no source of approved translations exists.
- `BL-060`, `BL-064`, `BL-066`, `BL-036` — re-scanned, unchanged, reasons in §4 / §6.6 / §9.

---

## 11. Amendment check

`AMEND-001` (2026-07-28) describes exactly this change and is **consistent with this design** — registry + aliases, `TEXT`/`TEXT[]` slugs on the four columns, hierarchy/region/culture/formality/styling-rules/date-rule/tier-gate/badge-colour metadata, `INSERT`-to-add. Two details this design adds that the amendment does not contradict and does not need rewriting for (the amendments log is append-only and never edited): `badge_color` is a design-token key rather than a hex, and the registry ships with a DB-level normalisation trigger plus an `occasion_unknown_tags` capture table. If a later ticket materially changes either, that gets its own amendment entry rather than an edit to `AMEND-001`.

---

**Risk: high** — this design creates and alters DB schema on a live project, drops a type and a table, adds RLS policies and `SECURITY DEFINER` functions, backfills user preference data, and changes occasion handling in seven already-shipped tickets. Every one of those is a §C2 one-way door.
