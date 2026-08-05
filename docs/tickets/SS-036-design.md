# SS-036 — Pattern & Fabric Registries — Design

Architect phase, 2026-08-05. Worktree: `StyleSense-SS-036`, branch `feature/SS-036-pattern-fabric-registries` (cut from `develop` @ `eda6025`).

Source ticket: `docs/tickets/raw/SS-036.md`. Spec it executes: `BL-079` (pattern/fabric half only — the colour half of that row is corrected and explicitly out of scope). Seed vocabulary source: `BL-064`. Structural precedents: `supabase/migrations/007_occasions_registry.sql` (registry/aliases/unknown-capture + normalisation functions), `008_occasion_columns_to_text.sql` (the `BEFORE INSERT OR UPDATE` trigger on `wardrobe_items` — the only prior instance of this exact pattern), `014_garment_types_registry.sql` (SS-034, the most recent sibling).

---

## 1. Scope restatement

Give `wardrobe_items.pattern` and `wardrobe_items.fabric` a canonical controlled vocabulary using the registry shape SS-025 proved and SS-034 most recently repeated: two registry tables (`patterns`, `fabrics`) keyed by a slug with a `^[a-z][a-z0-9_]*$` CHECK, two sibling alias tables, one shared unknown-capture table, `SECURITY DEFINER` normalisation functions with a pinned `search_path`, and — the part that makes this ticket materially different from SS-034 — a `BEFORE INSERT OR UPDATE` row trigger wired onto `wardrobe_items`, which is the live write path for every SS-012 vision-tagging call, every mobile tag edit, and (indirectly) every "Mark Worn" tap. The seed transcribes SS-012's existing Gemini prompt vocabulary verbatim from `BL-064`; no new vocabulary is invented. Every existing `pattern`/`fabric` value on the live project is normalised or captured by a one-time backfill in the same migration, with before/after counts recorded. Colour (`color_primary`/`color_secondary`) is **not** touched — those are hex strings parsed numerically by SS-027, a different problem class needing a hex→family binning decision first; `BL-064`'s colour half stays open.

The one non-negotiable property, above every other AC: **an out-of-vocabulary pattern/fabric string must never fail an otherwise-good write to `wardrobe_items`.** Everything in §3.4 exists to make that structurally true and provable rather than asserted.

---

## 2. Blast radius (why this is `Risk: high` and SS-034 was `med`)

| | SS-034 (`014`) | SS-036 (this ticket, `016`) |
|---|---|---|
| Existing tables altered | none | none (columns unchanged: still `TEXT`, still nullable, no FK added) |
| Existing rows rewritten | none | **yes** — one-time normalisation backfill of `wardrobe_items.pattern`/`.fabric` |
| Consumers of the new objects | none (grep-tested) | **a row trigger on `wardrobe_items`**, i.e. every SS-012 tagging write, every mobile tag edit, and every UPDATE the SS-015 wear-stats sync path issues |
| Failure mode if the design is wrong | dead tables | **a failed item write** — a user's upload silently erroring, or a Gemini tagging result lost after the money was already spent |

Concretely, the live write paths that will begin executing new trigger code the moment `016` is pushed:

1. `backend/services/wardrobe_tagging_service.py:309-320` → `WardrobeRepository.update_tagging_result` → `UPDATE wardrobe_items SET pattern = …, fabric = …` (SS-012, the money path — the Gemini call has already been paid for by the time this write happens).
2. `mobile/features/wardrobe/components/EditItemTagsForm.tsx:187-206` → free-text `Input`s for Pattern and Fabric → `wardrobe.service.ts` update.
3. `mobile/features/wardrobe/components/ReviewStep.tsx` (upload review save).
4. `supabase/migrations/006_wardrobe_item_wears.sql:51` — `sync_wardrobe_item_wear_stats()` issues `UPDATE wardrobe_items SET wear_count …, last_worn_at …` from an `AFTER` trigger on `wardrobe_item_wears`. **Every "Mark Worn" tap therefore fires a `BEFORE UPDATE` on `wardrobe_items`.** This is the hot path that dictates §3.4's `WHEN` clause; without it, an item holding an unknown fabric would re-log a capture row occurrence on every single wear.

---

## 3. Concrete values to use, not invent

### 3.0 Migration file and number

`supabase/migrations/016_pattern_fabric_registries.sql`.

Local migration files in this worktree top out at `015_wear_occasion_awareness.sql` (verified by directory listing, 2026-08-05), and the raw ticket's Technical Notes assign `016` after the 2026-07-31 Wave 1.5 renumbering (`012` SS-029, `013` SS-033, `014` SS-034, `015` SS-035). **I could not run `supabase migration list --linked` from this phase (no shell tool) — the number is verified against the repo, not against the live project.** The Developer must run `supabase migration list --linked` immediately before `db push`; if remote already holds a `016`, renumber to the next free slot, record the renumber in `docs/worklog/SS-036.md`, and report it. Do **not** apply the DDL out-of-band via `supabase db query` — that is exactly what produced the unrecorded-migration incident in `BL-110` (2026-07-31) and required a manual `migration repair`.

### 3.1 Tables

Five new tables. Names deliberately avoid `garment_unknown_types` (SS-034) and `occasion_unknown_tags` (SS-025) — see edge case 6 in the raw ticket.

```sql
CREATE TABLE patterns (
  key         TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  label       TEXT NOT NULL,
  labels_i18n JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active   BOOLEAN NOT NULL DEFAULT true,
  sort_order  INTEGER NOT NULL DEFAULT 100,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fabrics (
  key            TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  label          TEXT NOT NULL,
  labels_i18n    JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- Engine v2 fabric x weather attributes (see §3.6 for the decision).
  weight         TEXT     CHECK (weight IS NULL OR weight IN ('light','medium','heavy')),
  breathability  SMALLINT CHECK (breathability IS NULL OR breathability BETWEEN 0 AND 10),
  season_affinity TEXT[]  CHECK (
                    season_affinity IS NULL
                    OR (cardinality(season_affinity) > 0
                        AND season_affinity <@ ARRAY['summer','winter','monsoon'])),
  is_active      BOOLEAN NOT NULL DEFAULT true,
  sort_order     INTEGER NOT NULL DEFAULT 100,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_patterns_active_sort ON patterns (is_active, sort_order);
CREATE INDEX idx_fabrics_active_sort  ON fabrics  (is_active, sort_order);

CREATE TABLE pattern_aliases (
  alias       TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  pattern_key TEXT NOT NULL REFERENCES patterns(key) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE fabric_aliases (
  alias      TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  fabric_key TEXT NOT NULL REFERENCES fabrics(key) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pattern_aliases_key ON pattern_aliases (pattern_key);
CREATE INDEX idx_fabric_aliases_key  ON fabric_aliases  (fabric_key);

-- The AC's "shared *_unknown_tags capture table", read literally: ONE table
-- serving both registries, discriminated by `attribute`. Shared rather than
-- two tables so the eventual colour registry (BL-064's open half) widens a
-- CHECK instead of adding a third capture table.
CREATE TABLE attribute_unknown_tags (
  attribute      TEXT NOT NULL CHECK (attribute IN ('pattern','fabric')),
  slug           TEXT NOT NULL,
  occurrences    INTEGER NOT NULL DEFAULT 1,
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_source  TEXT,   -- 'wardrobe_items' | future writers, per 007's precedent
  sample_user_id UUID,   -- no FK, deliberately: a deleted user must not break capture
  PRIMARY KEY (attribute, slug)
);
```

**Deliberate deviations from `BL-079`'s literal column list, each flagged rather than smuggled in:**

- `labels_i18n` — present on `occasions` (007) and `garment_types` (014); included for consistency so a later ALTER isn't needed. Ships `'{}'` for every row: **no translations are invented** (`BL-090`'s root cause, not a new gap).
- `created_at` — same three-table precedent.
- The three `fabrics` attribute columns — the raw ticket's explicit open design question; decided in §3.6.
- `patterns` gets **no** attribute columns. See §9 open question 3.

**No foreign key from `wardrobe_items.pattern`/`.fabric` to these registries, ever.** An FK would turn an out-of-vocabulary Gemini string into a failed tagging write — the exact outcome the AC forbids. This absence is asserted by a test (§6.1 #27), not just stated here.

### 3.2 Seed — transcribed verbatim from `BL-064`, order preserved

Patterns (`sort_order` 10, 20, … in `BL-064`'s recorded order, which is also `gemini_vision_adapter.py:104-106`'s order):

| key | label | sort_order |
|---|---|---|
| `solid` | Solid | 10 |
| `stripes` | Stripes | 20 |
| `checks` | Checks | 30 |
| `floral` | Floral | 40 |
| `block_print` | Block Print | 50 |
| `bandhani` | Bandhani | 60 |
| `ikat` | Ikat | 70 |
| `paisley` | Paisley | 80 |
| `polka_dots` | Polka Dots | 90 |
| `embroidered` | Embroidered | 100 |
| `printed` | Printed | 110 |

Fabrics (`gemini_vision_adapter.py:107-109`'s order), with §3.6's attributes:

| key | label | sort_order | weight | breathability | season_affinity |
|---|---|---|---|---|---|
| `cotton` | Cotton | 10 | `light` | 9 | `{summer}` |
| `silk` | Silk | 20 | `medium` | 5 | `NULL` |
| `linen` | Linen | 30 | `light` | 10 | `{summer}` |
| `denim` | Denim | 40 | `heavy` | 2 | `{winter}` |
| `wool` | Wool | 50 | `heavy` | 1 | `{winter}` |
| `rayon` | Rayon | 60 | `light` | 6 | `{summer}` |
| `polyester` | Polyester | 70 | `light` | 2 | `{monsoon}` |
| `georgette` | Georgette | 80 | `light` | 5 | `{summer,monsoon}` |
| `chiffon` | Chiffon | 90 | `light` | 5 | `{summer}` |
| `khadi` | Khadi | 100 | `light` | 9 | `NULL` |
| `chikankari` | Chikankari | 110 | `light` | 8 | `{summer}` |

`NULL` `season_affinity` means **universal / no seasonal opinion**, exactly as `region_scope IS NULL` means pan-India in 007/014 — never "no seasons". `'all'` is deliberately **excluded** from the CHECK's value set so there is exactly one way to express "every season" (NULL); permitting both would recreate the null-vs-empty silent-failure mode 007's comments guard against. Note `season_tags` on `wardrobe_items` does use `'all'` — that is a different column with a different (shipped, unchanged) vocabulary; do not "harmonise" them.

`silk` and `khadi` carry `NULL` affinity on purpose: silk is occasion-driven rather than season-driven in Indian wear, and khadi's whole point is that it is cool in summer and warm in winter. Both are judgment calls, flagged in §9.

### 3.3 Alias seed — representative, not exhaustive (007/014's stated posture)

Every alias must already satisfy the `^[a-z][a-z0-9_]*$` CHECK, and must be disjoint from the canonical key set (asserted by test, not by constraint — Postgres has no cross-table CHECK). Anything a hyphen/space/case fold already resolves (`"Block-Print"` → `block_print`) needs **no** alias row; adding one would break the disjointness test.

```sql
INSERT INTO pattern_aliases (alias, pattern_key) VALUES
  ('plain','solid'), ('solids','solid'),
  ('striped','stripes'), ('stripe','stripes'),
  ('check','checks'), ('checked','checks'), ('checkered','checks'),
  ('chequered','checks'), ('plaid','checks'),
  ('florals','floral'), ('flowery','floral'),
  ('blockprint','block_print'), ('block_printed','block_print'),
  ('bandhej','bandhani'), ('bandhni','bandhani'),      -- bandhej: Gujarati/Rajasthani term
  ('ikkat','ikat'),
  ('paisleys','paisley'), ('ambi','paisley'),          -- ambi/keri: the Indian name
  ('polka_dot','polka_dots'), ('polkadots','polka_dots'),
  ('dots','polka_dots'), ('dotted','polka_dots'),
  ('embroidery','embroidered'),
  ('print','printed'), ('prints','printed'), ('digital_print','printed');

INSERT INTO fabric_aliases (alias, fabric_key) VALUES
  ('cottons','cotton'), ('pure_cotton','cotton'),
  ('silks','silk'), ('pure_silk','silk'), ('raw_silk','silk'),
  ('tussar_silk','silk'), ('banarasi_silk','silk'),    -- the ticket's own "tussar silk" example
  ('linens','linen'),
  ('jeans','denim'),
  ('woollen','wool'), ('woolen','wool'),
  ('viscose','rayon'), ('modal','rayon'), ('art_silk','rayon'),  -- art silk == artificial silk
  ('poly','polyester'), ('polyster','polyester'),
  ('georgett','georgette'),
  ('chifon','chiffon'),
  ('khaddar','khadi'),
  ('chikan','chikankari'), ('lucknowi','chikankari');
```

`tussar_silk → silk` is the literal resolution of the raw ticket's first edge case ("the vision model emits `"tussar silk"` → normalised if aliasable"). It is lossy at this vocabulary's granularity, and that is accepted: `BL-064` fixed the granularity, this ticket transcribes it.

### 3.4 Normalisation functions and the trigger

Seven functions. The contract is identical in spirit to 007/014, restated here so nobody re-opens those files:

1. trim → lower → collapse runs of whitespace and `-` to a single `_` → strip anything outside `[a-z0-9_]`; empty result → `NULL`.
2. if the result matches `patterns.key` / `fabrics.key` → use it.
3. else if it matches `pattern_aliases.alias` / `fabric_aliases.alias` → use the mapped key.
4. else → **keep** the normalised string. Never drop it. Never fail the write.

Step 2 before step 3 is what makes an alias/key collision inert.

```
public.attribute_normalize_shape(p_raw TEXT) -> TEXT
    LANGUAGE sql IMMUTABLE, SET search_path = public, pg_temp
    NOT security definer (touches no table). Body identical to
    occasion_normalize_shape / garment_normalize_shape. One shared shape
    function for both attributes rather than two copies.

public.attribute_log_unknown(p_attribute TEXT, p_slug TEXT, p_src TEXT, p_uid UUID) -> void
    LANGUAGE plpgsql, SECURITY DEFINER, SET search_path = public, pg_temp
    Single atomic INSERT ... ON CONFLICT (attribute, slug) DO UPDATE
      SET occurrences = attribute_unknown_tags.occurrences + 1, last_seen_at = now();
    Deliberately NOT a read-then-write (BL-036/BL-066: no third instance of that class).
    Returns early on a NULL slug.

public.pattern_is_known(p_slug TEXT) -> BOOLEAN   -- STABLE, SECURITY DEFINER, pinned path
public.fabric_is_known(p_slug TEXT)  -> BOOLEAN   -- STABLE, SECURITY DEFINER, pinned path

public.pattern_normalize_one(p_raw TEXT) -> TEXT  -- VOLATILE, SECURITY DEFINER, pinned path
public.fabric_normalize_one(p_raw TEXT)  -> TEXT  -- VOLATILE, SECURITY DEFINER, pinned path

public.wardrobe_items_normalize_pattern_fabric_trigger() -> TRIGGER
    LANGUAGE plpgsql, SECURITY DEFINER, SET search_path = public, pg_temp
```

**Who logs an unknown — one place, no ambiguity.** `pattern_normalize_one`/`fabric_normalize_one` **resolve only; they never write.** `attribute_log_unknown` is invoked from exactly one caller: the trigger function, which after resolving checks `NOT public.*_is_known(v_x)` and logs with real context (`TG_TABLE_NAME`, `NEW.user_id`). This deliberately differs from `garment_normalize_one` (014), which logs from inside itself with `NULL`/`NULL` context because it had no call site to get context from. Consequence to state in a comment in the migration: **any future non-trigger caller of `*_normalize_one` must call `attribute_log_unknown` itself**, or its unknowns go uncaptured. That is the trade for keeping the resolver pure (which is also what makes it safe to call twice, e.g. inside the backfill's `WHERE` and `SET` clauses, without double-counting).

**`VOLATILE`, not `STABLE` — a deliberate correction of SS-034's precedent.** `garment_normalize_one` (`014:447-494`) is declared `STABLE` while its step-4 branch `PERFORM`s a write. Postgres documents modifying the database from a `STABLE`/`IMMUTABLE` function as unwise/undefined `[trained-knowledge, not re-verified this pass]`; it is currently harmless there only because nothing calls it. Here `*_normalize_one` is pure and *could* honestly be `STABLE` — it is nevertheless declared `VOLATILE` so that a future edit adding a write inside it cannot silently inherit a wrong label on a live write path. Asserted by test (§6.1 #16). SS-034's mislabelling is logged as a backlog row (§8) rather than fixed from this ticket.

**Both `*_is_known` and the resolution step ignore `is_active`.** Resolution matches on key existence only. If resolution filtered on `is_active`, deactivating a registry row would instantly reclassify every existing item value holding that key as "unknown" and start capturing it — precisely the orphan/rewrite the raw ticket's edge case 5 forbids. `is_active` is a **pick-list / display flag only**. This is the single most likely thing for a future contributor to "fix" wrongly; say so in a comment in the migration, and assert it by test (§6.1 #30).

Trigger function body — every requirement below is load-bearing:

- Fast exit: `IF NEW.pattern IS NULL AND NEW.fabric IS NULL THEN RETURN NEW; END IF;`
- Resolve into **local variables first** (`v_pattern`, `v_fabric`), assign to `NEW.*` only after both calls have returned. This guarantees the failure path below leaves `NEW` exactly as the caller wrote it, rather than half-rewritten.
- After assigning, for each non-NULL resolved value that `NOT public.*_is_known(...)`, call `public.attribute_log_unknown('pattern'|'fabric', v_x, TG_TABLE_NAME, NEW.user_id)`.
- Wrap the whole body in `EXCEPTION WHEN OTHERS THEN RAISE WARNING 'SS-036 pattern/fabric normalisation skipped: %', SQLERRM; RETURN NEW; END;`. This is the structural guarantee behind the AC "an out-of-vocabulary fabric string still cannot fail an otherwise-good tagging result": whatever goes wrong inside normalisation (missing capture table, permission change, a future CHECK someone adds), the item write proceeds with the caller's original values and a server-log warning. `WHEN OTHERS` does not trap `query_canceled`/`assert_failure` `[trained-knowledge]`, which is the desired behaviour — a cancelled statement should stay cancelled. Note also that the handler rolls back the implicit subtransaction, so a capture-row write is lost on the failure path; the item write surviving is the correct trade and should be commented as such.

Triggers — **two, not one**, so the hot path is filtered declaratively:

```sql
CREATE TRIGGER trg_wardrobe_items_normalize_pattern_fabric_ins
  BEFORE INSERT ON wardrobe_items
  FOR EACH ROW EXECUTE FUNCTION public.wardrobe_items_normalize_pattern_fabric_trigger();

CREATE TRIGGER trg_wardrobe_items_normalize_pattern_fabric_upd
  BEFORE UPDATE ON wardrobe_items
  FOR EACH ROW
  WHEN (NEW.pattern IS DISTINCT FROM OLD.pattern
        OR NEW.fabric IS DISTINCT FROM OLD.fabric)
  EXECUTE FUNCTION public.wardrobe_items_normalize_pattern_fabric_trigger();
```

A single `BEFORE INSERT OR UPDATE` trigger (008's shape) cannot carry this `WHEN` clause, because the expression would reference `OLD` on the INSERT path. The split is what keeps `sync_wardrobe_item_wear_stats()`'s `UPDATE wardrobe_items SET wear_count …` (§2, fires on every Mark Worn tap) from re-entering plpgsql at all — and, more importantly, from re-incrementing `attribute_unknown_tags.occurrences` for an item that merely holds an unknown fabric. 008's occasion trigger has no such filter and does re-run on every unrelated UPDATE; that is a real (low-severity) defect in the shipped occasion capture counts, logged in §8 rather than fixed here.

Both new trigger names sort after `trg_wardrobe_items_normalize_occasions`, so the occasion trigger fires first. The two touch disjoint columns, so ordering is irrelevant — but it is asserted by test (§6.1 #24) rather than assumed.

### 3.5 One-time backfill of existing rows

Ordering inside `016` matters: **tables → seed → functions → backfill → CREATE TRIGGER.** Creating the triggers last means the backfill's own `UPDATE` does not re-enter them and cannot double-count captures.

Two passes, in one `DO` block, with `RAISE NOTICE` reporting:

```sql
DO $$
DECLARE v_captured INT := 0; v_normalised INT := 0;
BEGIN
  -- Pass 1: CAPTURE. Every distinct non-null value that resolves to neither a
  -- key nor an alias gets an attribute_unknown_tags row (with one sample
  -- user_id, MIN(user_id) over the matching rows). Values already in canonical
  -- shape (e.g. 'tussar_silk' typed lowercase) are untouched by pass 2, so
  -- capture MUST be its own pass or they would be silently uncaptured.
  --   for each of SELECT DISTINCT pattern / DISTINCT fabric WHERE x IS NOT NULL:
  --     v_shaped := attribute_normalize_shape(x)
  --     if v_shaped IS NOT NULL and NOT *_is_known(*_normalize_one(x)) then
  --       attribute_log_unknown('pattern'|'fabric', *_normalize_one(x),
  --                             'wardrobe_items', <sample user_id>)
  --       v_captured := v_captured + 1

  -- Pass 2: REWRITE, only where normalisation actually changes the value.
  UPDATE wardrobe_items
     SET pattern = public.pattern_normalize_one(pattern),
         fabric  = public.fabric_normalize_one(fabric)
   WHERE (pattern IS NOT NULL AND pattern IS DISTINCT FROM public.pattern_normalize_one(pattern))
      OR (fabric  IS NOT NULL AND fabric  IS DISTINCT FROM public.fabric_normalize_one(fabric));
  GET DIAGNOSTICS v_normalised = ROW_COUNT;

  RAISE NOTICE 'SS-036 backfill: % rows rewritten, % distinct unknown values captured',
               v_normalised, v_captured;
END $$;
```

Calling `*_normalize_one` twice per row (once in `WHERE`, once in `SET`) is safe precisely because §3.4 made the resolvers pure — no double-counted captures.

The `WHERE` clause keeps the backfill from touching rows that need nothing: no unnecessary row churn on the live project, and no unnecessary firing of `trg_wardrobe_items_normalize_occasions` (which would otherwise re-run occasion normalisation across the whole table).

`BL-064` predicts near-lossless normalisation because Gemini is already instructed to emit exactly this vocabulary. **Verify that against the live table rather than assuming it** — §5 makes the before/after capture a required, recorded step.

### 3.6 Fabric attributes for Engine v2 — decided, not deferred

**Decision: land `weight` / `breathability` / `season_affinity` on `fabrics` now, in this migration, seeded for all 11 rows (§3.2).** The ticket asks for an explicit recommendation rather than an assumption; this is it.

Why:

- The columns are **inert this ticket** — nothing reads `fabrics.*` at all; only `fabrics.key` is consulted, by the normalisation function. They add exactly zero to this ticket's actual risk surface, which is entirely the trigger.
- The cheapest moment to author 11 rows' worth of attributes is the moment the 11 rows are first written. That is SS-034's own §8 reasoning (`BL-109`: retrofit cost rises the instant the rows exist), applied to the direct analogue — and SS-034 is the precedent this ticket is told to follow.
- Engine v2's fabric×weather rule (velvet in Chennai in May, synthetics in Mumbai monsoon) is the stated reason this ticket exists at all: the proposal's "monsoon logic needs no migration" claim was only half true because there was no vocabulary. Shipping a vocabulary with no attributes reproduces the same half-truth one layer up.
- Cost of being wrong is an `UPDATE`, not a migration: the values are ordinals and a small closed enum, tunable with no schema change and no deploy — the property that already makes `occasions.formality` safe (007's own seed comment).

What this decision explicitly does **not** claim: that the seeded values are correct. They are Architect judgment in the same class as `occasions.formality` and `garment_types.base_formality`, flagged for stylist review before any scoring code consumes them (§8's `BL-125`, §9 open question 2).

---

## 4. Files to create/modify

| Path (all under the SS-036 worktree root) | Action |
|---|---|
| `supabase/migrations/016_pattern_fabric_registries.sql` | **new** — everything in §3.1–§3.5, in that order, plus a `ROLLBACK:` comment block in the 007/014 house style (drop triggers → drop functions → drop the five tables; note the backfill's value rewrite is **not** reversible from the rollback block, which is why §5's before-fixture is mandatory). |
| `backend/tests/test_db_schema.py` | **modify** — append the §6.1 tests at the end of the file. Do **not** create a new schema-test module: every prior ticket's schema tests live in this one file, gated by the existing module-level `pytestmark = skipif not SUPABASE_DB_URL`. |
| `backend/scripts/ss036_verify_pattern_fabric_registry.py` | **new** — live end-to-end verification against the linked project, following `ss035_verify_wear_occasion.py`'s shape. See §6.3. |
| `mobile/types/supabase.ts` | **regen** after the push (`supabase gen types`), SS-034/SS-035 precedent. Expect only this migration's five tables in the diff; if sibling objects from an unmerged Wave 1.5 branch appear, stop and report per `BL-110` rather than committing them silently. |
| `docs/worklog/SS-036.md` | **append** per phase (Architect entry written this pass). |

**No file under `backend/` (other than tests/scripts) or `mobile/` (other than the generated types) is created or modified.** In particular `wardrobe_tagging_service.py`, `wardrobe_repository.py`, `gemini_vision_adapter.py`, `wardrobe.service.ts` and `EditItemTagsForm.tsx` are untouched — see §7 edge case 8 for why no application-layer normaliser is added (unlike SS-025's boundary matrix / SS-035's boundary 7).

---

## 5. Applying it

Established practice (SS-025/SS-029/SS-033/SS-034/SS-035): the **Developer** applies with `supabase db push` against the linked project `mefpfykuinasgkpfhmzk` during the Developer phase, then confirms `supabase db diff --linked` is empty.

Required sequence, in order:

1. `supabase migration list --linked` → confirm `016` is free (§3.0). If not, renumber and report.
2. **Capture the before-fixture into `docs/worklog/SS-036.md` before pushing** (this is the AC's "asserted against a before/after fixture", and the only recovery path for a backfill the rollback block cannot undo):
   ```sql
   SELECT id, pattern, fabric FROM wardrobe_items ORDER BY id;
   SELECT pattern, count(*) FROM wardrobe_items GROUP BY 1 ORDER BY 2 DESC NULLS LAST;
   SELECT fabric,  count(*) FROM wardrobe_items GROUP BY 1 ORDER BY 2 DESC NULLS LAST;
   ```
3. `supabase db push`. Capture the `RAISE NOTICE` counts from §3.5 into the worklog.
4. Re-run the three queries; assert row count unchanged, no `id` lost, and every non-NULL before-value now either equals a registry key, or has a matching `attribute_unknown_tags` row, or was an all-punctuation string that became NULL (§7 edge case 4 / test 21).
5. `supabase db diff --linked` → empty. `BL-110` is live risk, not hypothetical (it already fired once, 2026-07-31): expect sibling Wave 1.5 objects if another branch has pushed. **Report the exact diff; never loosen `.github/workflows/supabase-migrations.yml`'s filter** — `BL-060`'s standing directive, already violated-and-fixed once. Serialize the push against any other Wave 1.5 ticket pushing the same day (SS-037 is code-only and adds no migration, so contention this round is limited to a stale remote history).

---

## 6. Test plan

### 6.1 `backend/tests/test_db_schema.py` (append; live-DB, gated on `SUPABASE_DB_URL`)

| # | Test | Asserts |
|---|---|---|
| 1 | `test_pattern_fabric_registry_tables_exist` | `patterns`, `fabrics`, `pattern_aliases`, `fabric_aliases`, `attribute_unknown_tags` all present in `information_schema.tables` |
| 2 | `test_pattern_and_fabric_key_shape_check_rejects_bad_slugs` | inserting `key = 'Block Print'` and `key = '1solid'` each raise `CheckViolation`; a well-shaped key succeeds |
| 3 | `test_patterns_seeded_with_exactly_the_eleven_bl064_keys` | the `patterns.key` set equals the 11 keys in §3.2 — set equality, so both a missing and an invented row fail |
| 4 | `test_fabrics_seeded_with_exactly_the_eleven_bl064_keys` | same for `fabrics.key` |
| 5 | `test_pattern_and_fabric_aliases_are_disjoint_from_their_keys` | `pattern_aliases.alias ∩ patterns.key = ∅`; same for fabric |
| 6 | `test_fabric_weight_check_is_closed` | `weight = 'bogus'` raises `CheckViolation`; `NULL` and `'medium'` succeed |
| 7 | `test_fabric_breathability_range_check` | `11` and `-1` raise; `0` and `10` succeed |
| 8 | `test_fabric_season_affinity_rejects_empty_array_and_the_all_token` | `'{}'` raises; `'{all}'` raises (documents §3.2's deliberate exclusion); `'{summer,monsoon}'` and `NULL` succeed |
| 9 | `test_canonical_key_wins_over_a_colliding_alias` | inside a rolled-back transaction, insert `pattern_aliases('solid' → 'floral')` — a deliberate collision with the canonical key `solid`; `pattern_normalize_one('solid')` still returns `'solid'`, not `'floral'`. Collision is inert **by resolution order**, not by any constraint (mirrors `007`'s `test_canonical_key_wins_over_a_colliding_alias`) |
| 10 | `test_pattern_normalize_one_maps_shape_and_aliases` | `'  Block-Print '` → `'block_print'`; `'Bandhej'` → `'bandhani'`; `'POLKA DOTS'` → `'polka_dots'` |
| 11 | `test_fabric_normalize_one_maps_shape_and_aliases` | `'Tussar Silk'` → `'silk'` (the raw ticket's own example); `'viscose'` → `'rayon'`; `'Pure Cotton'` → `'cotton'` |
| 12 | `test_normalize_one_keeps_an_unknown_slug_and_writes_nothing` | `fabric_normalize_one('Handloom Jamdani')` returns `'handloom_jamdani'` **and** creates no `attribute_unknown_tags` row — §3.4's "resolvers are pure; only the trigger logs" |
| 13 | `test_attribute_unknown_tags_key_is_attribute_plus_slug` | the same slug logged under `'pattern'` and under `'fabric'` yields two independent rows |
| 14 | `test_attribute_log_unknown_increments_on_repeat` | two calls with the same `(attribute, slug)` → one row, `occurrences = 2` (atomic upsert, no read-then-write) |
| 15 | `test_pattern_fabric_functions_are_security_definer_with_a_pinned_search_path` | `pattern_normalize_one`, `fabric_normalize_one`, `pattern_is_known`, `fabric_is_known`, `attribute_log_unknown`, `wardrobe_items_normalize_pattern_fabric_trigger` all have `prosecdef = true` and `proconfig` containing `search_path=public, pg_temp`; `attribute_normalize_shape` has the pinned path and is **not** SECURITY DEFINER |
| 16 | `test_normalize_one_functions_are_volatile_not_stable` | `pg_proc.provolatile = 'v'` for both `*_normalize_one` — §3.4's deliberate divergence from 014 |
| 17 | `test_trigger_normalises_pattern_and_fabric_on_insert` | inserting a `wardrobe_items` row with `pattern = 'Block Print'`, `fabric = 'COTTON '` reads back `'block_print'`, `'cotton'` |
| 18 | `test_trigger_normalises_pattern_and_fabric_on_update` | updating an existing row to `fabric = 'Tussar Silk'` reads back `'silk'` |
| 19 | **`test_out_of_vocabulary_fabric_does_not_fail_the_item_write`** | insert with `fabric = 'Handloom Jamdani'` **succeeds**; the row exists; `fabric = 'handloom_jamdani'`; an `attribute_unknown_tags` row exists with `attribute = 'fabric'`, `occurrences = 1`, `sample_source = 'wardrobe_items'`, `sample_user_id` = the row's owner. **The ticket's headline AC** |
| 20 | `test_null_pattern_and_fabric_stay_null` | insert with both `NULL` → both still `NULL`, no coercion to a default, no capture row |
| 21 | `test_all_punctuation_pattern_becomes_null_and_is_not_captured` | `pattern = '***'` → `NULL`; no `attribute_unknown_tags` row (nothing capturable) — matches `015`'s `test_all_punctuation_slug_becomes_null` precedent |
| 22 | `test_an_unrelated_update_does_not_reinflate_unknown_occurrences` | with a row holding an unknown fabric, run `UPDATE wardrobe_items SET brand = brand` → `occurrences` unchanged. Proves the `WHEN` clause |
| 23 | `test_wear_stats_sync_update_does_not_re_enter_the_normalisation_trigger` | insert a `wardrobe_item_wears` row for an item holding an unknown fabric (fires `006`'s `UPDATE wardrobe_items SET wear_count …`) → `occurrences` unchanged, `pattern`/`fabric` unchanged, `wear_count` correctly incremented. The concrete hot-path proof from §2 |
| 24 | `test_occasion_normalisation_still_works_alongside_the_new_triggers` | one INSERT carrying `occasion_tags = '{wedding}'` **and** `pattern = 'Block Print'` → reads back `{wedding_guest}` **and** `block_print`. No regression to SS-025's shipped trigger |
| 25 | `test_rls_enabled_on_all_five_new_tables` | `pg_class.relrowsecurity` true for all five |
| 26 | `test_only_select_policies_exist_on_the_four_readable_registry_tables` | exactly one `SELECT`-only policy on each of `patterns`/`fabrics`/`pattern_aliases`/`fabric_aliases`; **zero** policies on `attribute_unknown_tags` (absence of a policy *is* the write protection) |
| 27 | `test_no_foreign_key_from_wardrobe_items_pattern_or_fabric` | no FK constraint references `patterns`/`fabrics` from `wardrobe_items` — §3.1's "never fail a write" guarantee asserted structurally, so a future contributor can't add one silently |
| 28 | `test_every_existing_item_value_is_a_key_or_a_captured_unknown` | for every distinct non-NULL `pattern`/`fabric` in `wardrobe_items`: it equals a registry key **or** has a matching `attribute_unknown_tags` row. The standing form of the AC's before/after fixture |
| 29 | **`test_item_write_survives_a_broken_capture_table`** | inside one transaction: `ALTER TABLE attribute_unknown_tags RENAME TO attribute_unknown_tags_x`; insert a `wardrobe_items` row with an unknown fabric → the insert **still succeeds** and the fabric is stored normalised; then `ROLLBACK`. Proves §3.4's `EXCEPTION WHEN OTHERS` guard empirically instead of by inspection |
| 30 | `test_deactivating_a_registry_row_does_not_orphan_existing_values` | inside one transaction: `UPDATE patterns SET is_active = false WHERE key = 'ikat'`; `pattern_normalize_one('ikat')` still returns `'ikat'`; an item write with `pattern = 'Ikat'` still stores `'ikat'` and logs no capture row; `ROLLBACK`. Raw ticket edge case 5, and §3.4's most-likely-to-be-wrongly-"fixed" invariant |

Tests that mutate the live project (9, 29, 30, and every insert-based test) must run inside a transaction that is rolled back, or clean up their own rows — the existing file's `db_conn` fixture convention governs; follow it, don't invent a second one.

### 6.2 No purely-additive grep test

SS-034 shipped `test_garment_registry_purely_additive.py` because "nothing reads these tables" was its literal AC. That test would be **wrong here** — this ticket's registry *is* consumed, by the trigger. The equivalent guarantee for SS-036 is "no application source file changes", which is visible in the diff and asserted by §4, plus tests 19/23/24 proving the shipped write paths still behave.

### 6.3 `backend/scripts/ss036_verify_pattern_fabric_registry.py` + manual QA

Live script (follows `ss035_verify_wear_occasion.py`): against the linked project, using the service-role connection, inside a transaction it rolls back — create a throwaway user + wardrobe item, write `fabric = 'Handloom Jamdani'` and `pattern = 'Block-Print'` through a real insert, print the stored values and the resulting `attribute_unknown_tags` rows, then roll back. It prints for an operator to read; it does not silently exit 0.

Manual QA, in addition:

1. **RLS both directions**: `INSERT INTO patterns …` with an `authenticated` JWT fails with a row-level-security error; the same insert with `service_role` succeeds. Repeat for `fabrics`. Confirm `SELECT` works for `authenticated` on all four readable tables and fails on `attribute_unknown_tags`.
2. **SS-012 end-to-end, not simulated**: run the real `POST /wardrobe/tag` path against a real photo (the `BL-058`/`BL-067` lesson: no synthetic shortcuts), and confirm the resulting row's `pattern`/`fabric` are canonical slugs and the tagging response is otherwise unchanged. This is the AC "SS-012's tagging path keeps working unchanged" — it must be *observed*, not inferred from unit tests.
3. **Mobile edit round-trip**: type `"Raw Silk"` into `EditItemTagsForm`'s Fabric field, save, and observe what the UI shows after the refetch. Expected: `silk`. Record whether React Query's cached value flickers before settling (§7 edge case 9) — an observation to report, not a pass/fail gate.
4. **Drift check** (§5 step 5) and the before/after fixture (§5 steps 2/4) recorded in the worklog.

---

## 7. Edge cases

Carried forward from the raw ticket (1–6), plus what the current codebase state adds (7–11).

1. **OOV fabric (`"tussar silk"`)** → `tussar_silk` is an *alias* and resolves to `silk` (§3.3); a genuinely unknown one (`"handloom jamdani"`) is stored normalised **and** captured. The item write succeeds either way. Tests 11, 19.
2. **Existing value differing only by case/whitespace/plural** → handled by the shape step + alias rows; the migration reports normalised-vs-captured counts via `RAISE NOTICE` (§3.5). Test 28, plus §5's fixture.
3. **`NULL` pattern/fabric** (tagging failed or in progress, SS-005 processing status) → stays `NULL`; the trigger fast-exits. Test 20.
4. **A slug colliding with an alias** → inert by resolution order (key wins first), enforced by test, never by constraint. Test 9.
5. **Deactivating a registry row** → `is_active` is not consulted by resolution, so no existing item value is orphaned or rewritten. Test 30. Loudly commented in the migration.
6. **Name collision with SS-034's `garment_unknown_types`** → avoided by using a single shared `attribute_unknown_tags` with an `attribute` discriminator (§3.1), which also leaves room for `BL-064`'s colour half to widen the CHECK rather than add a third capture table.
7. **(new) The wear-stats sync path fires a `BEFORE UPDATE` on `wardrobe_items` on every Mark Worn tap** (`006:51`). Without the `WHEN` filter this would re-run normalisation and re-increment capture occurrences on an unrelated write. Handled by the two-trigger split (§3.4). Tests 22, 23.
8. **(new) No application-layer normaliser is added, deliberately** — unlike SS-025's `BL-078` boundary matrix and SS-035's boundary 7, which normalise client-side *and* in the DB. Reasons: this is a `Risk: high` ticket whose entire risk is the trigger, and adding TS/Python implementations of the same contract puts three new copies of it on the live tagging path in one PR; the tagging path already emits in-vocabulary values by construction (`gemini_vision_adapter.py:104-109`); and there is no client-side pick-list to validate against yet. The cost is edge case 9. Logged for follow-up (`BL-127`), not silently assumed away.
9. **(new) A user's free-typed pattern/fabric now round-trips as a slug.** `EditItemTagsForm.tsx:187-206` are plain text `Input`s, so typing `"Raw Silk"` reads back `silk`. Display-wise this is not a regression — `ItemDetailSheet.tsx:380-385` already renders the raw column value and Gemini already writes `block_print`-style slugs today — but the *edit* experience changes. Verified manually at QA (§6.3 item 3); the durable fix (registry-driven pickers + `label` display) is `BL-127`.
10. **(new) An empty-string pattern/fabric becomes `NULL`.** The edit form binds `value={draft.pattern ?? ''}`, so a cleared field can persist `''`; `attribute_normalize_shape('')` returns `NULL`. This is an improvement (`''` and `NULL` stop being two ways to say "unset") but it *is* a behaviour change on a shipped path — noted, not hidden. Test 21 covers the adjacent all-punctuation case.
11. **(new) Vocabulary-quality observations, flagged and deliberately not fixed.** `chikankari` is an embroidery technique, not a fibre; `khadi` is a handloom process; `embroidered` is a technique sitting in a pattern list; and `printed` is a superset of `block_print`, so a garment can honestly match both. These are `BL-064`'s recorded vocabulary and the AC says transcribe, don't invent — the same posture SS-034 took with `kanjeevaram` ("an attribute wearing a type's clothing"). Flagged in §9 for whoever owns vocabulary quality.

---

## 8. Backlog deltas

I cannot edit `docs/BACKLOG.md` from this worktree — apply these in the main checkout. **ID-collision warning:** the banner (2026-08-04) says `develop` tops out at `BL-122` and that SS-036/SS-037's Architect passes both append from that baseline in parallel. I have reserved **`BL-123`–`BL-127`**; SS-037's Architect will likely have reserved the same range. Reconcile by hand before applying, same precedent as the `BL-097`–`BL-106` collision.

**Resolve:**

- **`BL-079` → Resolved.** Resolved by: SS-036 / Architect, 2026-08-05. Note: *"Pattern/fabric half built verbatim as specified — `patterns`/`fabrics` registries with slug PK + `^[a-z][a-z0-9_]*$` CHECK, `pattern_aliases`/`fabric_aliases`, a shared `attribute_unknown_tags` capture table, `SECURITY DEFINER` normalisation functions with pinned `search_path`, `SELECT`-only RLS, and `BEFORE INSERT`/`BEFORE UPDATE` triggers on `wardrobe_items` (see `docs/tickets/SS-036-design.md`). The row's own 2026-07-30 correction is honoured: colour is out of scope and stays open under `BL-064`."*

**Keep Active, with a re-scan note:**

- **`BL-064`** — *"Re-scanned by SS-036 / Architect (2026-08-05): pattern/fabric half RESOLVED (canonical registries + alias normalisation + capture landed in migration `016`; seed transcribed verbatim from this row's recorded prompt vocabulary). The `color_primary`/`color_secondary` half stays open and is now this row's entire remaining subject — it needs a hex→colour-family binning decision first, per `BL-079`'s correction."*
- **`BL-060`** — *"Re-scanned by SS-036 / Architect (2026-08-05): stays Active. Migration `016` adds five tables, seven functions and two triggers; design §5 restates the standing directive to report the exact `db diff` and never loosen the filter."*
- **`BL-110`** — *"Re-scanned by SS-036 / Architect (2026-08-05): stays Active, unresolved. SS-036 is the last of Wave 1.5's four migrations (`016`). Design §3.0 requires `supabase migration list --linked` immediately before push and forbids out-of-band `supabase db query` DDL (the 2026-07-31 incident); still a convention, not a mechanism."*
- **`BL-090`** — *"Re-scanned by SS-036 / Architect (2026-08-05): `patterns.labels_i18n`/`fabrics.labels_i18n` ship `'{}'` for the same reason as occasions' and garment_types'. Same root cause, not a new row."*

**New Active rows:**

- **`BL-123`** (tag `schema`, source SS-036 / Architect, 2026-08-05) — *"`garment_normalize_one` (SS-034, `014_garment_types_registry.sql:447-494`) is declared `STABLE` but writes to `garment_unknown_types` via `garment_log_unknown` in its step-4 branch. Postgres treats database modification from a `STABLE`/`IMMUTABLE` function as unwise/undefined. Harmless today because nothing calls that function (SS-034's registry is inert), but it becomes a live latent bug the moment Wave 2 wires a consumer. SS-036 does not repeat it — its `*_normalize_one` functions are pure and declared `VOLATILE`, asserted by test. Fix is a one-line `CREATE OR REPLACE` in a future migration."*
- **`BL-124`** (tag `schema`, source SS-036 / Architect, 2026-08-05) — *"`occasion_unknown_tags.occurrences` counts are inflated by unrelated writes. `trg_wardrobe_items_normalize_occasions` (`008:75-77`) is a single `BEFORE INSERT OR UPDATE` trigger with no unchanged-value `WHEN` filter, so every `UPDATE wardrobe_items` re-runs `occasion_normalize_array` — including the `sync_wardrobe_item_wear_stats()` write (`006:51`) that fires on every Mark Worn tap. An item holding an unknown occasion slug therefore re-increments its capture row on every wear. Low severity (the counts are a review signal, not a decision input) but it makes 'how often does the model emit this?' unreliable. SS-036 avoids the class by splitting into `BEFORE INSERT` + `BEFORE UPDATE … WHEN (NEW.x IS DISTINCT FROM OLD.x)`; the same split would fix `008`."*
- **`BL-125`** (tag `ai`, source SS-036 / Architect, 2026-08-05) — *"Seeded `fabrics.weight`/`breathability`/`season_affinity` values (11 rows, `016`) are Architect judgment, not stylist- or data-validated — same class as `occasions.formality`, `garment_types.base_formality` and `BL-097`'s empty `styling_rules`. Two deliberate `NULL`s need a second opinion: `silk` (occasion-driven rather than season-driven in Indian wear) and `khadi` (cool in summer, warm in winter). Nothing reads these columns yet, so a wrong value costs an `UPDATE` — but Engine v2's fabric×weather rule consumes them directly, so they need a review pass before that scoring ships. Folds naturally into `BL-077`'s post-launch eval work."*
- **`BL-126`** (tag `ai`, source SS-036 / Architect, 2026-08-05) — *"`patterns` ships with no attribute columns, unlike `fabrics`. Engine v2's fabric×weather rule was the stated driver for fabric attributes; if the engine ever scores pattern *mixing* or pattern *scale* (busy-with-busy, small-scale-with-large-scale), `patterns` will need an analogous column set (e.g. `scale`, `busyness`) and the same 'author it while the rows are new' argument applies. Deliberately not invented in SS-036 — the ticket flagged only fabric attributes and no proposal section pins a pattern attribute shape. Decide before Engine v2's scoring stage is designed."*
- **`BL-127`** (tag `infra`, source SS-036 / Architect, 2026-08-05) — *"No registry-driven UI for pattern/fabric, and no label display. `EditItemTagsForm.tsx:187-206` are free-text `Input`s and `ItemDetailSheet.tsx:380-385` renders the raw column value, so after SS-036 a user who types \"Raw Silk\" sees `silk` on the next refetch, and canonical values render as `block_print` rather than `Block Print`. Neither is a regression (Gemini already writes slugs), but SS-036 deliberately shipped DB-side normalisation only — no application-layer normaliser, unlike SS-025's `BL-078` boundary matrix — to keep a `Risk: high` trigger ticket's blast radius bounded. The follow-up is a picker/typeahead driven by `patterns`/`fabrics` plus `label`-based display, which also removes the round-trip surprise. Natural owner: whichever ticket next touches wardrobe filters/facets (the original motivation in `BL-064`)."*

Nothing else in the Active table's `schema`/`ai`/`ci`/`infra` rows is resolvable by this ticket. `BL-117` (no `regions`/`cultures` vocabulary) is adjacent but untouched — SS-036 adds no region/culture columns.

---

## 9. Open questions / blockers

**No hard blocker: nothing this ticket depends on is missing.** SS-012 and SS-025 are shipped, the registry precedent is concrete, and the seed vocabulary is already recorded. `Risk: high` means the full lane, so these are for the human gate before the Developer starts:

1. **Migration number `016` is verified against the repo, not the live project** (§3.0). I had no shell tool this phase. Run `supabase migration list --linked` before the Developer phase begins if possible — a taken slot changes the file name, and the incident history says silent renumbering is how `BL-110`'s incident escalated.
2. **The 11 seeded fabric attribute values are my judgment** (§3.6, `BL-125`). If the reviewer would rather ship the three columns unseeded (all `NULL`), or drop them and let Engine v2 add them, that is a clean fallback: delete the three columns and their CHECKs from §3.1 and the last three columns from §3.2's table. Nothing else in the design changes.
3. **`patterns` gets no attribute columns** (`BL-126`) — asymmetric with `fabrics` on purpose, because only fabric attributes were named as an Engine v2 need. Flagging in case the reviewer wants symmetry now rather than a second migration later.
4. **No application-layer normalisation** (§7 edge case 8, `BL-127`). A genuine deviation from SS-025's stated `BL-078` posture — SS-035 explicitly chose "both halves, not trigger-only" for the analogous new write boundary. I chose trigger-only because the risk being managed here *is* the trigger, and three parallel implementations of one contract shipped alongside a live-path trigger is the wrong thing to add to a `Risk: high` diff. If the reviewer disagrees, the answer is `BL-127`, not a redesign.
5. **The vocabulary itself is imperfect** (§7 edge case 11) — `chikankari`/`khadi` are techniques, `printed` overlaps `block_print`. The AC forbids inventing new vocabulary, so it ships as recorded. Said out loud at the gate rather than discovered in Engine v2.
6. **The backfill is not reversible from the rollback block.** `016`'s rollback comment can drop every object it creates, but it cannot restore a pre-normalisation `pattern`/`fabric` string. That is why §5 step 2's before-fixture is mandatory and must land in the worklog *before* `db push`, not after.

---

## 10. Risk classification

**Risk: high — confirmed, not revised.**

Self-attack, per the instruction to classify up when on the fence — and the fence is not close here. This design (a) installs row triggers on `wardrobe_items`, the live write path for SS-012's paid tagging call, the mobile upload-review save, the item-edit save, and every wear-stats sync; (b) rewrites existing rows on the live shared project (`mefpfykuinasgkpfhmzk`) in a way the migration's own rollback block cannot undo; (c) creates `SECURITY DEFINER` functions and RLS policies. Each is independently on §C2's named one-way-door list, and the failure mode is not cosmetic — a wrong trigger silently drops a Gemini result that was already paid for, or fails a user's upload.

The design's answer to that risk is structural rather than procedural: resolve-into-locals-then-assign so a failure leaves the row untouched, an `EXCEPTION WHEN OTHERS` guard proven by a rollback-scoped test that actually breaks the capture table (§6.1 #29), a `WHEN` clause keeping the hot path out of plpgsql entirely, no FK anywhere near the consuming columns (asserted by test), `is_active` deliberately excluded from resolution, pure resolvers so the backfill can call them twice safely, and a mandatory before-fixture recorded ahead of the push. None of that lowers the classification — it is what a `high` classification is supposed to buy.
