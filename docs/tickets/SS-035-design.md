# SS-035 — Occasion-Aware Wear History (`occasion_key` + `outfit_id`) — Design

Ticket: [`docs/tickets/raw/SS-035.md`](raw/SS-035.md) · `[Infra]` `[P1]` `[Sprint 5]` `[3 pts]` · Depends on SS-015, SS-025
Source: [`docs/proposals/STYLING-ENGINE-V2.md`](../proposals/STYLING-ENGINE-V2.md) §9 Wave 1.5 item 3 (novelty scoring, §5 stage ③)
Architect pass: 2026-08-04 (Opus — full lane; the raw ticket already carries `Risk: high`)

**This document is the Developer's spec.** Every value in it is fixed. Where a value is my own judgement (nothing upstream pins it) it says so inline. Do not re-open the proposal or the raw ticket to re-derive anything below.

---

## 1. Scope restatement

`wardrobe_item_wears` (`006_wardrobe_item_wears.sql`, SS-015) records `item_id`, `user_id`, `worn_on`, `created_at` and nothing else, so "how recently was this worn" is a single global number. SS-035 adds two nullable columns — `occasion_key` (which occasion the item was worn *for*) and `outfit_id` (which outfit it was part of) — so recency becomes occasion-scoped: *"you wore this kurta to `office` on Tuesday, but it is fresh for `festival`."* That is the memory input Engine v2's stage-③ novelty term needs, and it is what lets a deterministic engine stop repeating itself without becoming non-deterministic (the input changes daily; same-input-same-output still holds).

Two additive columns is the easy half. The hard half is that this table is **not** inert: its `UNIQUE (item_id, worn_on)` constraint *is* `BL-071`'s idempotency guarantee, it sits directly upstream of the `AFTER INSERT/UPDATE/DELETE` trigger that recomputes `wardrobe_items.wear_count`, and `wear_count` is the input to the `cost_per_wear` **`GENERATED ALWAYS … STORED`** money column (`001_initial.sql:63-68`). The confirmed product decision (2026-07-30: one item may be logged for two different occasions on the same date) forces that constraint to widen, and a naive widening re-opens `BL-071` because Postgres treats every `NULL` as distinct in a unique index. Everything else in this design follows from getting that one constraint right.

This ticket ships **schema + read substrate + the Mark Worn occasion picker**. It does **not** wire the styling engine: `backend/services/outfit_suggestion_service.py` and `backend/services/styling_rules_engine.py` are untouched (`BL-096`'s live landmine; the `BL-102`/SS-033 precedent for staying out). AC #6 is satisfied by shipping a *queryable, indexed, tested* answer, not by consuming it.

---

## 2. Files to create / modify

### 2.1 Create

| Path | Purpose |
|---|---|
| `supabase/migrations/015_wear_occasion_awareness.sql` | Pre-assigned number (§3). Version gate, derived-cache snapshot guard, the two columns, the widened constraint, the composite FK + its prerequisite `outfits` unique constraint, indexes, the `occasion_key` normalisation trigger, the `wear_recency()` read function, comments. |
| `backend/adapters/wear_history_repository.py` | `SupabaseWearHistoryRepository(IWearHistoryRepository)` — RLS-scoped anon+JWT client, calls `wear_recency` via RPC, never raises. |
| `backend/tests/test_wear_history_repository.py` | Row mapping, RLS-scoping pin, never-raises, NULL-occasion semantics. |
| `backend/scripts/ss035_verify_wear_occasion.py` | Manual live verification (§8), same shape as `ss015_verify_wear_history.py` / `ss033_verify_impression_logging.py`. |
| `mobile/features/wardrobe/components/WearOccasionField.tsx` | Optional occasion picker for the Add-a-wear / edit-a-wear cards. |
| `mobile/__tests__/features/wardrobe/components/WearOccasionField.test.tsx` | Component tests (§7.4). |

### 2.2 Modify

| Path | Change |
|---|---|
| `backend/adapters/interfaces.py` | Add `WearRecency` dataclass + `IWearHistoryRepository`, alongside `IOccasionRepository`/`IAppConfigRepository`/`ISuggestionLogRepository`. Existing ports untouched. |
| `backend/tests/test_db_schema.py` | New SS-035 section (§7.1). `wardrobe_item_wears` is deliberately **not** added to `EXPECTED_TABLES` — SS-015 kept it out and SS-025/SS-033 set the precedent of a dedicated test block instead. |
| `mobile/features/wardrobe/wardrobe.service.ts` | `logWardrobeItemWear` / `updateWardrobeItemWear` gain `occasionKey`; normalise it on write (§5.1). |
| `mobile/features/wardrobe/wardrobe.queries.ts` | Widen `LogWardrobeItemWearInput` / `UpdateWardrobeItemWearInput`. |
| `mobile/features/wardrobe/wardrobe.types.ts` | `LogWearResult` gains `occasionKey`. `WardrobeItemWearRow` is `Tables<'wardrobe_item_wears'>` and picks the new columns up for free once the types are regenerated — **do not hand-add them** (CLAUDE.md). |
| `mobile/features/wardrobe/wardrobe.constants.ts` | Five new copy constants (§4). |
| `mobile/features/wardrobe/components/WearHistorySection.tsx` | Render each wear's occasion; occasion picker in the add and edit cards. |
| `mobile/__tests__/features/wardrobe/components/WearHistorySection.test.tsx` | Extend (§7.4). |
| `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` | Extend (§7.4). |
| `mobile/types/supabase.ts` | Regenerate — **conditionally**, see §9 Q4 (the parallel-worktree hazard, SS-033 Q3's precedent). |

### 2.3 Explicitly **not** touched

- `backend/services/outfit_suggestion_service.py`, `backend/services/styling_rules_engine.py`, `backend/routers/outfit_suggestions.py` — `BL-096`'s landmine; SS-020 / Engine v2 owns the wiring. No novelty term is added to any scorer here.
- `mobile/features/wardrobe/components/ItemDetailSheet.tsx`'s **primary "Mark Worn" button** — it keeps writing `occasion_key = NULL` in one tap. The ticket's Technical Notes require occasion selection to be optional; making the primary tap a two-step flow would contradict that. See §9 Q3.
- `001_initial.sql` and `006_wardrobe_item_wears.sql` — never edited (`BL-060`). Every change is forward-only in `015`.
- `wardrobe_items.wear_count` / `last_worn_at` / `cost_per_wear` and the `sync_wardrobe_item_wear_stats` trigger — **no definition changes.** §3.2 proves they are unchanged rather than assuming it.

### 2.4 Port placement rationale

`IWearHistoryRepository` goes in **`backend/adapters/interfaces.py`**, not `backend/ai/ports/interfaces.py`: `ai/ports/` is scoped by CLAUDE.md to AI *provider capabilities* (`IVisionProvider`, `IStylingProvider`, `ISearchProvider`); this is a Postgres persistence port, the same kind as `IWardrobeRepository`/`IOccasionRepository`/`IAppConfigRepository`/`ISuggestionLogRepository` already in that file. It is a **new** port rather than three more methods on `IWardrobeRepository` because the consumer is the styling engine (not the upload/tagging pipeline `IWardrobeRepository` serves), it is read-only where that port is write-heavy, and SS-033 set the precedent of one port per new read/log surface. No new folder is invented.

---

## 3. Migration `015_wear_occasion_awareness.sql`

**Number confirmed.** Live Wave 1.5 map, per `docs/tickets/raw/SS-033.md`'s Technical Notes and `BL-110`'s incident note (renumbered 2026-07-31 after SS-029 shipped as `012`, `011` having gone to SS-028): `012` SS-029, `013` SS-033, `014` SS-034, **`015` SS-035**, `016` SS-036. `[VERIFIED 2026-08-04 — this worktree's `supabase/migrations/` tops out at `013_suggestion_impressions.sql`; `014` belongs to the SS-034 worktree and is not present here.]`

### 3.1 The version gate — first statement in the file

Two of this migration's statements need **PostgreSQL 15 or newer**:

1. `UNIQUE NULLS NOT DISTINCT (…)` — §3.3.
2. `ON DELETE SET NULL (outfit_id)` on a composite FK — §3.4.

`[trained-knowledge — both were introduced in PostgreSQL 15; MUST be confirmed against the live server, not assumed. See §9 Q1 and `docs/OPERATOR_RULEBOOK.md` §E / `BL-001`.]`

```sql
DO $$
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'SS-035 requires PostgreSQL 15+ (UNIQUE NULLS NOT DISTINCT, ON DELETE SET NULL (column)); '
      'this server reports %. Use the documented <15 fallback in docs/tickets/SS-035-design.md 3.8.',
      current_setting('server_version');
  END IF;
END $$;
```

This gate is not decoration. Without it, a `<15` server rejects the DDL with a bare syntax error at whichever statement it reaches first, after some of the migration has already applied. With it, the migration fails on its first statement with a message that names the cause and the fallback.

### 3.2 Derived-cache guard (AC #5), self-verifying

AC #5 requires `wear_count`, `last_worn_at` and `cost_per_wear` to be **unchanged for every pre-existing row**. Rather than a fixture captured in a separate script that someone can forget to run, the migration asserts it on itself — the same fail-loudly posture as `008_occasion_columns_to_text.sql:104-116`'s GIN-survival guard:

```sql
-- Plain TEMP table, deliberately NOT `ON COMMIT DROP`: whether the Supabase CLI
-- wraps a migration in a single transaction is not something this file should
-- depend on. A session-scoped temp table is correct either way, and it is
-- dropped explicitly at the end of this file.
CREATE TEMP TABLE ss035_wear_stats_before AS
  SELECT id, wear_count, last_worn_at, cost_per_wear FROM public.wardrobe_items;
```

…and, as the last statement before the temp table is dropped:

```sql
DO $$
DECLARE v_bad INTEGER;
BEGIN
  SELECT count(*) INTO v_bad
  FROM ss035_wear_stats_before b
  JOIN public.wardrobe_items a ON a.id = b.id
  WHERE a.wear_count   IS DISTINCT FROM b.wear_count
     OR a.last_worn_at IS DISTINCT FROM b.last_worn_at
     OR a.cost_per_wear IS DISTINCT FROM b.cost_per_wear;
  IF v_bad > 0 THEN
    RAISE EXCEPTION 'SS-035 altered a derived wear statistic on % pre-existing row(s); AC #5 violated', v_bad;
  END IF;
  IF (SELECT count(*) FROM ss035_wear_stats_before)
     <> (SELECT count(*) FROM public.wardrobe_items) THEN
    RAISE EXCEPTION 'SS-035 changed the wardrobe_items row count';
  END IF;
END $$;

DROP TABLE ss035_wear_stats_before;
```

`IS DISTINCT FROM`, not `<>`, so a `NULL`→`NULL` comparison is correctly "same" and a `NULL`→value change is correctly "different". Expected to pass trivially: `ADD COLUMN` with no default is a catalogue-only operation on PG11+, and nothing here touches `wardrobe_items` other than adding a `UNIQUE` constraint to `outfits`. The guard exists because "expected to pass" is not "passed".

### 3.3 The widened uniqueness constraint — the whole risk of this ticket

`006:28` today:

```sql
CONSTRAINT wardrobe_item_wears_one_per_day UNIQUE (item_id, worn_on)
```

Replaced by:

```sql
ALTER TABLE public.wardrobe_item_wears
  DROP CONSTRAINT wardrobe_item_wears_one_per_day;

ALTER TABLE public.wardrobe_item_wears
  ADD CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion
    UNIQUE NULLS NOT DISTINCT (item_id, worn_on, occasion_key);
```

Four things the Developer must not get wrong:

1. **Syntax placement.** For a *table constraint* the modifier precedes the column list: `UNIQUE NULLS NOT DISTINCT (a, b, c)`. (For `CREATE UNIQUE INDEX` it trails the column list instead.) The raw ticket writes it in the index form; the constraint form above is what goes in the file. `[trained-knowledge — confirm against the server's own parser, which the migration run does implicitly.]`
2. **`NULLS NOT DISTINCT` is the entire `BL-071` preservation mechanism.** Under the default `NULLS DISTINCT`, `(item, 2026-08-04, NULL)` can be inserted an unbounded number of times — every repeat tap of the one-tap "Mark Worn" button (which writes `NULL`) would insert a new row and inflate `wear_count`, i.e. exactly the complaint SS-015 was built to fix, silently reintroduced by a widening that *looks* conservative. §7.1 has a test that inserts the same `NULL`-occasion row twice and asserts the second is rejected.
3. **It is a widening, so no existing row can violate it.** Today at most one row exists per `(item_id, worn_on)`; adding a third column to the key can only make collisions rarer. No data cleanup, no `NOT VALID`/`VALIDATE` dance.
4. **Constraint name changes**, deliberately: `wardrobe_item_wears_one_per_day` is now a false description. The new name is `wardrobe_item_wears_one_per_day_per_occasion`, and it is referenced by name in the fallback RPC (§5.2) and in §7.1's tests.

**Ordering that makes this correct:** the normalisation trigger (§3.6) is `BEFORE INSERT OR UPDATE`, and Postgres evaluates `BEFORE` row triggers before constraint checks. So `'Work'`, `'work'` and `'office'` all become `office` *before* uniqueness is tested, and a same-day repeat under any spelling collapses. Without that ordering, alias spellings would each open their own idempotency bucket. Tested in §7.1.

### 3.4 The two new columns

```sql
ALTER TABLE public.wardrobe_item_wears
  ADD COLUMN occasion_key TEXT,
  ADD COLUMN outfit_id    UUID;

ALTER TABLE public.wardrobe_item_wears
  ADD CONSTRAINT wardrobe_item_wears_occasion_key_shape_check
    CHECK (occasion_key IS NULL OR occasion_key ~ '^[a-z][a-z0-9_]*$');
```

- **Both nullable, no default.** This *is* AC #7's backfill: every pre-existing row gets `occasion_key = NULL` (= unknown occasion) with no `UPDATE` statement, and `NULL` is a permanent, valid, first-class state — a user who just taps "worn" produces one.
- **The shape CHECK is what stops a second "unknown" bucket forming.** Without it an empty string could be stored, and `''` and `NULL` would be two distinct non-occasions under the widened key. The regex is byte-identical to `occasions.key`'s own CHECK (`007:37`). Because the normalisation trigger runs first and returns `NULL` for anything that normalises to nothing, **the CHECK can never reject a user's raw input** — it only pins the trigger's output shape. That is why it is safe to have a strict CHECK on a column whose whole point is accepting unknown values.

**No foreign key from `occasion_key` to `occasions(key)` — and this deviates from the letter of the raw ticket's edge-case list, which says "`ON DELETE RESTRICT` on the registry side."** Flagged rather than silently chosen, per `docs/OPERATOR_RULEBOOK.md`:

- An FK is **flatly incompatible with AC #1** ("unknowns kept and captured — never dropped, **never a failed write**") and with the ticket's own edge case "an unknown/unmapped occasion slug on write → stored + captured". A referential constraint turns exactly that case into a `23503` write failure.
- It is also inconsistent with every other occasion column in this schema: `wardrobe_items.occasion_tags` (`TEXT[]`), `outfits.occasion`, `social_posts.occasion` and `suggestion_sessions.occasion` all became plain `TEXT` in `008` with **no** FK, precisely so the `occasion_unknown_tags` capture path could exist. SS-025's `ON DELETE RESTRICT` appears only on `occasions.parent_key` — a registry-internal edge, not a consumer edge.
- The *outcome* the edge case wants — "historical wear rows must survive with their recorded key; history is not re-writable" — is delivered **more** strongly by having no FK than by `RESTRICT`: with no FK there is nothing to cascade, nothing to restrict, and a registry row's deletion or deactivation is structurally incapable of touching history. The registry's supported way to retire an occasion is `is_active = false` anyway, which never touched wear rows either way.

**`outfit_id` uses this repo's composite-FK convention** (`006:22-24`'s precedent, which required `006:13-14`'s `UNIQUE (id, user_id)` on `wardrobe_items`):

```sql
-- Prerequisite for the composite FK below; additive, mirrors 006:13-14.
ALTER TABLE public.outfits
  ADD CONSTRAINT outfits_id_user_id_key UNIQUE (id, user_id);

ALTER TABLE public.wardrobe_item_wears
  ADD CONSTRAINT wardrobe_item_wears_outfit_fk
    FOREIGN KEY (outfit_id, user_id)
    REFERENCES public.outfits (id, user_id)
    ON DELETE SET NULL (outfit_id);
```

Three points, one of which is a trap:

- **`ON DELETE SET NULL (outfit_id)`, with the column list, is mandatory — not a stylistic choice.** A bare `ON DELETE SET NULL` on a composite FK sets *every* referencing column to `NULL`, including `user_id`, which is `NOT NULL` (`006:19`). Deleting an outfit would then fail with a not-null violation, breaking AC #2 ("deleting that outfit does not delete or alter the wear row") in the noisiest possible way. The single-column form is a PostgreSQL 15 feature — the same gate as §3.3, which is convenient: one version check covers both.
- **`ON DELETE SET NULL`, never `CASCADE`.** The wear happened even if the outfit is later deleted; cascading would delete real wear rows, which the `AFTER DELETE` trigger would then turn into a lowered `wear_count` and a silently *raised* `cost_per_wear`. `outfit_id` becoming `NULL` leaves `wear_count` and `cost_per_wear` untouched, which is what AC #2 and §7.1's test require.
- **`MATCH SIMPLE` (the default) is what makes a `NULL` `outfit_id` legal.** With any referencing column `NULL`, the constraint is not checked, so the overwhelmingly common "no outfit" case costs nothing. The corollary: a legacy `outfits` row with `user_id IS NULL` (the column is nullable, `001:82`) can never be referenced. There are no such rows to worry about — `[VERIFIED 2026-08-04 — ripgrep over this worktree: nothing in `mobile/`, `backend/` or `supabase/functions/` writes `outfits`; the only references are `mobile/types/supabase.ts`, `weekly-report/index.ts`'s count, and `test_db_schema.py`]`, consistent with `SS-025-design.md` §6.4's "0 rows, no code". Developer confirms the row count in §8 step 2 before adding the constraint.

### 3.5 Indexes

```sql
CREATE INDEX idx_item_wears_user_occasion_worn
  ON public.wardrobe_item_wears (user_id, occasion_key, worn_on DESC);   -- wear_recency()'s occasion-filtered aggregate
CREATE INDEX idx_item_wears_outfit_id
  ON public.wardrobe_item_wears (outfit_id) WHERE outfit_id IS NOT NULL; -- the ON DELETE SET NULL scan path
```

- `006:31`'s `idx_item_wears_item_worn_on (item_id, worn_on DESC)` and `006:32`'s `idx_item_wears_user_id (user_id)` are **kept unchanged**; the widened constraint brings its own `(item_id, worn_on, occasion_key)` index with it.
- **`idx_item_wears_outfit_id` is load-bearing, not speculative.** Postgres does not automatically index the referencing side of a foreign key, and every `DELETE FROM outfits` now scans `wardrobe_item_wears` to apply `SET NULL`. Same lesson SS-033 §3.3 recorded for its cascade path. Partial (`WHERE outfit_id IS NOT NULL`) because until SS-020/SS-023 exist, ~100% of rows have `NULL` here and indexing them buys nothing.

### 3.6 The `occasion_key` normalisation trigger — the new `BL-078` boundary

`008:51-73`'s `occasion_scalar_normalize_trigger` is hardcoded to a column literally named `occasion`, so it cannot be reused. A **new dedicated function**, not a parameterised one:

```sql
CREATE OR REPLACE FUNCTION public.wear_occasion_key_normalize_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_norm TEXT;
BEGIN
  IF NEW.occasion_key IS NULL THEN
    RETURN NEW;
  END IF;

  v_norm := public.occasion_normalize_one(NEW.occasion_key);

  IF v_norm IS NOT NULL AND NOT public.occasion_is_known(v_norm) THEN
    PERFORM public.occasion_log_unknown(v_norm, TG_TABLE_NAME, NEW.user_id);
  END IF;

  NEW.occasion_key := v_norm;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_wardrobe_item_wears_normalize_occasion_key
  BEFORE INSERT OR UPDATE ON public.wardrobe_item_wears
  FOR EACH ROW EXECUTE FUNCTION public.wear_occasion_key_normalize_trigger();
```

**Dedicated rather than parameterised via `TG_ARGV`, deliberately.** A parameterised version would have to build its assignment with `EXECUTE`, and `007_occasions_registry.sql:166-171` states the invariant for this whole family of privileged objects in capitals: *"These are privileged objects: they take only text/uuid arguments, execute no dynamic SQL, and write exactly one table. KEEP THEM THAT WAY."* A `SECURITY DEFINER` function running dynamic SQL is a materially different security object. Twenty duplicated lines is the cheaper trade.

Behaviour inherited from `occasion_normalize_one` (`007:194-232`), unchanged and not re-derived: shape-normalise → canonical key wins → alias lookup → otherwise keep the normalised slug and record it in `occasion_unknown_tags`. Never dropped, never a failed write. An all-punctuation input normalises to `NULL`, i.e. "no occasion" — the same degradation `occasion_scalar_normalize_trigger` already has.

`occasion_unknown_tags.sample_source` now takes a fifth value, `'wardrobe_item_wears'`. The column is plain `TEXT` with no CHECK, so nothing breaks; `007:85`'s enumerating comment is stale as of this migration and is superseded by §3.7's `COMMENT ON COLUMN` here (forward-only — `007` is never edited).

### 3.7 `wear_recency()` — the queryable answer to AC #6

PostgREST cannot express `GROUP BY`, and the two figures the AC distinguishes ("days since worn at all" vs "days since worn *for this occasion*") are one aggregate over the same rows. So this ships as a function rather than as two client queries or a Python-side aggregate over every wear row:

```sql
CREATE OR REPLACE FUNCTION public.wear_recency(
  p_user_id      UUID,
  p_occasion_key TEXT DEFAULT NULL
)
RETURNS TABLE (
  item_id                   UUID,
  last_worn_on              DATE,
  last_worn_on_for_occasion DATE,
  wears_for_occasion        INTEGER
)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
  SELECT w.item_id,
         MAX(w.worn_on)                                                    AS last_worn_on,
         MAX(w.worn_on) FILTER (WHERE w.occasion_key = p_occasion_key)     AS last_worn_on_for_occasion,
         COUNT(*) FILTER (WHERE w.occasion_key = p_occasion_key)::INTEGER  AS wears_for_occasion
  FROM public.wardrobe_item_wears w
  WHERE w.user_id = p_user_id
  GROUP BY w.item_id;
$$;
```

- **`SECURITY INVOKER` (the default), unlike the normalisation functions.** Those need elevation to write `occasion_unknown_tags` from inside a trigger. This one only reads rows the caller can already read, so RLS (`user_owns_item_wears`, `006:38-41`) stays in force and a user cannot read another user's history through it. Least privilege, same reasoning SS-033 §3.5 recorded for its derivation triggers. `p_user_id` is an explicit filter *in addition to* RLS, not instead of it — it exists so a future `service_role` caller is still scoped.
- **`NULL` means unknown, never a match — enforced by SQL's own three-valued logic, not by a convention someone must remember.** `w.occasion_key = p_occasion_key` is `NULL` (not true) whenever either side is `NULL`, so a backfilled row never satisfies the `FILTER`, and calling with `p_occasion_key => NULL` returns `last_worn_on_for_occasion = NULL` / `wears_for_occasion = 0` for every item. That is AC #7's second half, structurally. §7.1 tests both directions.
- **Returns dates, not day-counts.** "Today" is an IST question (CLAUDE.md's India rules; `worn_on` values are authored against `istTodayIso()` in `WearDateField`), and a server-side `CURRENT_DATE` is UTC. The caller subtracts against IST today using `backend/services/ist_window.py`. Putting the timezone decision in SQL would bury it.
- **Nothing calls this yet.** Same posture as SS-033's substrate: Engine v2 / SS-020 wires it. Logged so it does not become dead surface (§10, `BL-117`).

### 3.8 Fallback if the live server is `<15`

If §9 Q1 comes back below PostgreSQL 15, **stop and get sign-off before deviating** — then:

- **Constraint:** drop `wardrobe_item_wears_one_per_day` and create an expression index instead of a table constraint:
  `CREATE UNIQUE INDEX wardrobe_item_wears_one_per_day_per_occasion ON public.wardrobe_item_wears (item_id, worn_on, COALESCE(occasion_key, ''));`
  Same semantics (`NULL` collapses into one bucket per item/day), but **PostgREST cannot infer an expression index as an `ON CONFLICT` arbiter**, so the client write path *must* switch to the RPC in §5.2 — that is not optional in this branch.
- **FK:** replace the composite FK with `outfit_id UUID REFERENCES public.outfits(id) ON DELETE SET NULL`, plus a `BEFORE INSERT OR UPDATE` trigger asserting `outfit_id IS NULL OR EXISTS (SELECT 1 FROM outfits o WHERE o.id = NEW.outfit_id AND o.user_id = NEW.user_id)` to preserve the defence-in-depth the composite FK was providing. `outfits_id_user_id_key` is then unnecessary and should not be added.
- Record which branch was taken, and why, in the migration header and the worklog. Do not leave it to be inferred from the SQL.

### 3.9 Comments (machine-checkable, per §7.1)

```sql
COMMENT ON COLUMN public.wardrobe_item_wears.occasion_key IS
  'SS-035. Occasion this wear was FOR, normalised at the DB boundary by '
  'trg_wardrobe_item_wears_normalize_occasion_key (aliases mapped, unknown slugs kept and '
  'recorded in occasion_unknown_tags with sample_source = ''wardrobe_item_wears''). '
  'Deliberately NO foreign key to occasions(key): an unknown slug must never fail the write, '
  'and history must survive a registry change. NULL means UNKNOWN OCCASION and must NEVER be '
  'treated as a match for any occasion (see public.wear_recency).';

COMMENT ON COLUMN public.wardrobe_item_wears.outfit_id IS
  'SS-035. Outfit this wear was part of. ON DELETE SET NULL (outfit_id), never CASCADE: the '
  'wear happened even if the outfit is later deleted, and cascading would corrupt wear_count '
  'and the generated cost_per_wear. No writer exists yet - SS-020/SS-023 own it.';

COMMENT ON CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion ON public.wardrobe_item_wears IS
  'SS-035, widened from SS-015''s UNIQUE (item_id, worn_on). NULLS NOT DISTINCT is load-bearing: '
  'without it, unlimited NULL-occasion rows per item per day would re-open BL-071 by letting '
  'repeat "Mark Worn" taps inflate wear_count and halve cost_per_wear.';
```

### 3.10 Rollback block (file footer, `007`/`008`/`013`'s convention)

```sql
-- ROLLBACK (valid while nothing reads the new columns):
--   DROP FUNCTION IF EXISTS public.wear_recency(UUID, TEXT);
--   DROP TRIGGER IF EXISTS trg_wardrobe_item_wears_normalize_occasion_key ON public.wardrobe_item_wears;
--   DROP FUNCTION IF EXISTS public.wear_occasion_key_normalize_trigger();
--   DROP INDEX IF EXISTS idx_item_wears_outfit_id;
--   DROP INDEX IF EXISTS idx_item_wears_user_occasion_worn;
--   ALTER TABLE public.wardrobe_item_wears DROP CONSTRAINT wardrobe_item_wears_outfit_fk;
--   ALTER TABLE public.outfits DROP CONSTRAINT outfits_id_user_id_key;
--   ALTER TABLE public.wardrobe_item_wears DROP CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion;
--   ALTER TABLE public.wardrobe_item_wears DROP CONSTRAINT wardrobe_item_wears_occasion_key_shape_check;
--   ALTER TABLE public.wardrobe_item_wears DROP COLUMN outfit_id, DROP COLUMN occasion_key;
--   ALTER TABLE public.wardrobe_item_wears ADD CONSTRAINT wardrobe_item_wears_one_per_day UNIQUE (item_id, worn_on);
-- NOTE: the final statement FAILS if two same-day multi-occasion rows already exist. That is
-- correct - it means real user data now depends on the widening, and rolling back would have to
-- destroy a wear the user recorded. Resolve by hand, never by deleting rows to make it apply.
```

---

## 4. Concrete values to use, not invent

| Thing | Value | Source |
|---|---|---|
| Migration filename | `015_wear_occasion_awareness.sql` | raw ticket, Technical Notes (renumbered 2026-07-31) |
| New constraint name | `wardrobe_item_wears_one_per_day_per_occasion` | §3.3 (my call; the old name is now false) |
| Shape CHECK name | `wardrobe_item_wears_occasion_key_shape_check` | §3.4 |
| Slug regex | `^[a-z][a-z0-9_]*$` | `007_occasions_registry.sql:37`, byte-identical |
| Outfit FK name | `wardrobe_item_wears_outfit_fk` | §3.4 (matches `006`'s `…_item_fk` naming) |
| `outfits` unique constraint | `outfits_id_user_id_key` | mirrors `006:14`'s `wardrobe_items_id_user_id_key` |
| Trigger fn / trigger | `public.wear_occasion_key_normalize_trigger()` / `trg_wardrobe_item_wears_normalize_occasion_key` | §3.6 |
| Read function | `public.wear_recency(p_user_id UUID, p_occasion_key TEXT DEFAULT NULL)` | §3.7 |
| New indexes | `idx_item_wears_user_occasion_worn`, `idx_item_wears_outfit_id` | §3.5 |
| `unknown_tags` source value | `'wardrobe_item_wears'` | `TG_TABLE_NAME`, §3.6 |
| Normalisation contract | trim → lower → collapse `[space-]+`→`_` → strip non-`[a-z0-9_]`; key wins, then alias, else keep + capture | `007:153-171`, unchanged |
| Occasion registry keys | the 12 seeded in `007:122-134` + 8 aliases (`007:142-150`) | do not re-seed, do not extend |
| PostgreSQL floor | **15** (`NULLS NOT DISTINCT`, `ON DELETE SET NULL (col)`) | §3.1 |
| Shared Supabase project | `mefpfykuinasgkpfhmzk` | `BL-110`, `SS-025-design.md` |

**New mobile copy constants** (`wardrobe.constants.ts`) — mine, matching the tone of the existing `WEAR_*` block (`wardrobe.constants.ts:230-244`), which is not re-derived:

```ts
export const WEAR_OCCASION_FIELD_LABEL = 'Occasion (optional)';
export const WEAR_OCCASION_NONE_LABEL = 'No occasion';
export const WEAR_OCCASION_NONE_CHIP_LABEL = 'Any occasion';
export const WEAR_DUPLICATE_DATE_OCCASION_MESSAGE =
  'A wear is already logged for that date and occasion';
export const WEAR_OCCASIONS_UNAVAILABLE_MESSAGE =
  "Couldn't load occasions. You can still log this wear without one.";
```

`WEAR_DUPLICATE_DATE_MESSAGE` (`'A wear is already logged for that date'`) is **kept** and is still the right copy when no occasion is selected; the new message is used when one is. `WEAR_LOGGED_TODAY_MESSAGE` is unchanged — its meaning is now scoped to date **and** occasion, which reads correctly either way.

---

## 5. Application shape

### 5.1 Mobile write path (the `BL-078` app-layer half)

`wardrobe.service.ts` (`:411-427`, `:429-440`):

```ts
export async function logWardrobeItemWear(
  itemId: string,
  userId: string,
  wornOn: string,
  occasionKey: string | null = null,
): Promise<{ alreadyLogged: boolean }>

export async function updateWardrobeItemWear(
  wearId: string,
  wornOn: string,
  occasionKey: string | null,
): Promise<void>
```

- **Normalise before writing**, reusing the shipped helper rather than a new one: `occasionKey` goes through `resolveOccasionKey(raw, (await readCachedTaxonomies())?.payload)` from `features/onboarding/onboarding.occasions.ts` — the same helper `normalizeOccasionTagsForWrite` (`wardrobe.service.ts:513-518`) already wraps for `occasion_tags`. An empty result becomes `null`. A slug the cached snapshot does not know is passed through unchanged (shape-normalised) and the DB trigger resolves or captures it. **Never dropped, never a failed write** — the SS-025 §6.4 contract, applied to boundary 7.
- **Upsert conflict target widens** to `{ onConflict: 'item_id,worn_on,occasion_key', ignoreDuplicates: true }`. `.select()` still returns only genuinely-inserted rows, so `alreadyLogged` keeps working with no change of shape.
- The optional 4th parameter keeps every existing call site (`ItemDetailSheet.tsx:269-271`'s one-tap Mark Worn) compiling and behaving identically — it writes `NULL`, which is a valid state, not a validation error.

Both defaults are chosen so the *quick* path stays one tap. `wardrobe.queries.ts`'s three mutation hooks widen their input interfaces to carry `occasionKey`; cache invalidation is unchanged.

### 5.2 Fallback write path (only if §8 step 4 shows arbiter inference fails, or under §3.8)

`[trained-knowledge — MUST be verified, not assumed: whether Postgres/PostgREST `ON CONFLICT` arbiter inference selects a `NULLS NOT DISTINCT` unique constraint from a bare column list. If it does not, the upsert silently degrades to a plain insert and duplicates appear — a quiet failure, exactly the class §C2's gates exist to catch.]` If it fails, add to `015`:

```sql
CREATE OR REPLACE FUNCTION public.log_wardrobe_item_wear(
  p_item_id      UUID,
  p_worn_on      DATE,
  p_occasion_key TEXT DEFAULT NULL,
  p_outfit_id    UUID DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE v_id UUID;
BEGIN
  INSERT INTO public.wardrobe_item_wears (item_id, user_id, worn_on, occasion_key, outfit_id)
  VALUES (p_item_id, auth.uid(), p_worn_on, p_occasion_key, p_outfit_id)
  ON CONFLICT ON CONSTRAINT wardrobe_item_wears_one_per_day_per_occasion DO NOTHING
  RETURNING id INTO v_id;
  RETURN v_id;   -- NULL means "already logged for this item/date/occasion"
END;
$$;
```

`SECURITY INVOKER` (the default) so `user_owns_item_wears`' `WITH CHECK` still applies; `user_id` comes from `auth.uid()` rather than the caller, which also removes the client's ability to write a wear onto someone else's item. `logWardrobeItemWear` then becomes `supabase.rpc('log_wardrobe_item_wear', …)` and `alreadyLogged = data === null`. Name the arbiter **by constraint**, not by column list — that is what makes it immune to the inference question.

### 5.3 Mobile read/edit surface

- **`WearOccasionField.tsx`** — a horizontal `Badge` chip row built from `useOccasionOptions().optionsIncluding(value ? [value] : [])` (the SS-025 union rule, so an unknown or deactivated slug on an existing row stays visible and selected instead of being silently stripped on the next save), plus a leading `WEAR_OCCASION_NONE_LABEL` chip that clears the selection. Selecting the already-selected chip also clears it. Loading → the field renders disabled with a spinner; error → `WEAR_OCCASIONS_UNAVAILABLE_MESSAGE` and the wear can still be logged without an occasion (CLAUDE.md: every component handles loading/error/empty; and an occasion picker that fails must never block a wear).
- **`WearHistorySection.tsx`** — each `WearRow` renders the occasion as a `Badge` using `occasionLabel(...)` / `occasionBadgeColor(...)` for the label and colour, falling back to `humanizeOccasionSlug` for an unknown slug (never a raw slug, never a blank chip — SS-025 §8 edge cases 9/10). A `NULL` occasion renders `WEAR_OCCASION_NONE_CHIP_LABEL` as a neutral `Text variant="caption" color="secondary"`, not a coloured badge, so "unknown" is visibly not an occasion. The add-a-wear card and the edit card both include `WearOccasionField`. A `23505` on edit now surfaces `WEAR_DUPLICATE_DATE_OCCASION_MESSAGE` when an occasion is selected and the existing `WEAR_DUPLICATE_DATE_MESSAGE` when it is not; `isUniqueViolation` (`:44-51`) is unchanged.
- **No `outfit_id` UI.** There is no outfit surface in the app at all (§3.4's verification), so a picker would have nothing to pick. Schema-only, `BL-118`.

### 5.4 Backend read port

```python
@dataclass(frozen=True)
class WearRecency:
    item_id: str
    last_worn_on: date | None
    last_worn_on_for_occasion: date | None   # NULL means "never worn for this occasion"
    wears_for_occasion: int


class IWearHistoryRepository(ABC):
    """(SS-035) Read-only occasion-scoped wear recency for novelty scoring.

    RLS-scoped via the caller's JWT (the SupabaseOccasionRepository /
    SupabaseWardrobeRepository shape), NOT service_role: this is the user's own
    wardrobe data, read on their behalf, inside their own request.

    MUST NEVER RAISE. 'No history' degrades to 'no novelty penalty', never to a
    failed suggestion request -- the same posture as
    ISuggestionLogRepository.recent_impressions.
    """

    @abstractmethod
    async def fetch_wear_recency(
        self, *, jwt: str, user_id: str, occasion_key: str | None = None
    ) -> list[WearRecency]:
        """One row per item the user has ever worn, newest-first is NOT
        guaranteed (the caller indexes by item_id). Returns [] on any failure."""
```

`SupabaseWearHistoryRepository` calls `.rpc("wear_recency", {"p_user_id": user_id, "p_occasion_key": occasion_key})`, maps rows to `WearRecency`, wraps the whole body in `try/except Exception`, logs `wear_recency_fetch_failed` at ERROR, returns `[]`. Client construction mirrors `adapters/occasion_repository.py:29-34` exactly (anon key + `.postgrest.auth(jwt)`).

---

## 6. Edge cases

Every case from the ticket, carried forward with its resolution, plus what the current codebase adds.

### From the ticket

1. **Same item, same day, two different occasions → both rows accepted.** The widened key includes `occasion_key`; `('office')` and `('puja')` are distinct. §7.1.
2. **Same item, same day, same occasion, repeat taps → idempotent.** The widened `UNIQUE` still collides; the client's `ignoreDuplicates` upsert returns zero rows → `alreadyLogged = true`. `wear_count` unchanged. §7.1, §7.4.
3. **One `NULL`-occasion row and one `'office'` row on the same day → allowed, but `NULL` duplicates are not.** `NULLS NOT DISTINCT` (§3.3) is the whole mechanism. Two tests, one for each half.
4. **An occasion later deactivated or deleted from the registry** → historical rows keep their recorded key because there is no FK (§3.4). Pickers hide an inactive occasion but the union rule (§5.3) keeps it visible and selected on a row that carries it.
5. **Unknown/unmapped slug on write** → shape-normalised, stored, and recorded in `occasion_unknown_tags`; never dropped, never a failed write (§3.6). §7.1.
6. **Backfilled `NULL` rows must never count as a match** → SQL three-valued logic in `wear_recency`'s `FILTER` (§3.7), plus the `COMMENT ON COLUMN` stating it in the schema itself. §7.1.
7. **Deleting an outfit → wear rows survive with `outfit_id = NULL`; `wear_count`/`cost_per_wear` unchanged.** `ON DELETE SET NULL (outfit_id)` (§3.4). The column-list form is what stops it failing on the `NOT NULL user_id`. §7.1.
8. **A wear for an item the user has since deleted** → `006:22-24`'s `ON DELETE CASCADE` is unchanged and not touched by this ticket.

### Found in the current codebase

9. **A bare `ON DELETE SET NULL` on the composite FK would make outfit deletion fail outright** (`user_id` is `NOT NULL`). §3.4. This is the single most likely way to implement AC #2 and get the opposite of it.
10. **The raw ticket's `ON DELETE RESTRICT`-on-the-registry edge case contradicts its own AC #1.** Resolved as "no FK" with reasons in §3.4; flagged, not silently chosen.
11. **`wear_count` semantics change for multi-occasion days.** The trigger (`006:46-61`) is `COUNT(*)`, so an item worn for two occasions on one day now counts **2**, and `cost_per_wear` drops accordingly. Previously one day could only ever be 1. This is a change to a **money** figure (`BL-075`'s class) and is a product decision, not an implementation detail — §9 Q2. The design keeps `COUNT(*)`; the alternative (`COUNT(DISTINCT worn_on)`) is spelled out there.
12. **A `NULLS NOT DISTINCT` constraint may not be inferable as a PostgREST `ON CONFLICT` arbiter.** If it is not, the upsert silently becomes an insert and duplicates appear with no error. Verified in §8 step 4; fallback in §5.2.
13. **`occasion_unknown_tags.sample_source`'s enumerating comment (`007:85`) is now stale** — a fifth table writes it. No CHECK exists, so nothing breaks; corrected forward in §3.9 rather than by editing `007`.
14. **`ItemDetailSheet`'s one-tap Mark Worn writes `NULL` forever unless the user opens Wear history.** By design (occasion must be optional), but it means the signal this ticket exists to collect may stay sparse. §9 Q3, `BL-119`.
15. **`WardrobeItemWearRow` is `Tables<'wardrobe_item_wears'>`** — every new field arrives only when `mobile/types/supabase.ts` is regenerated, which §9 Q4 makes conditional. If the regen is deferred, the mobile changes will not typecheck. Sequencing matters; §8 step 6.
16. **Four Wave 1.5 migrations target one live project** (`BL-110`). `supabase db diff --linked` will report siblings' objects as drift. Report the exact diff; never loosen the CI filter (`BL-060`).
17. **A wear row could be edited to point at an outfit the user does not own** — prevented by the composite FK's `(outfit_id, user_id)` pair, which is precisely why `006` adopted the convention. Under §3.8's fallback the equivalent guard is a trigger, and must not be dropped.

---

## 7. Test plan

Pytest (+ live-DB gate) and Jest/RNTL per CLAUDE.md. Each AC is named against the test that covers it.

### 7.1 `backend/tests/test_db_schema.py` (modify — live-DB-gated, `BL-005`)

New SS-035 block, following the SS-025/SS-033 sections' style. `wardrobe_item_wears` stays out of `EXPECTED_TABLES`.

| Test | Asserts | AC |
|---|---|---|
| `test_wear_occasion_key_and_outfit_id_columns_exist` | both columns, nullable, `text`/`uuid` | 1, 2 |
| `test_server_version_is_at_least_15` | `server_version_num >= 150000` — the gate, asserted rather than assumed | — |
| `test_widened_unique_constraint_exists_and_is_nulls_not_distinct` | constraint by name; `pg_index.indnullsnotdistinct` is true | 3, 4 |
| `test_old_one_per_day_constraint_no_longer_exists` | the narrowing actually landed | 3 |
| `test_same_item_same_day_two_occasions_both_insert` | two rows accepted | **3** |
| `test_same_item_same_day_same_occasion_second_insert_is_rejected` | `23505` | **4** |
| `test_same_item_same_day_two_null_occasion_rows_are_rejected` | `23505` — the `BL-071` regression guard | **4** |
| `test_wear_count_is_not_inflated_by_a_rejected_duplicate` | `wear_count` after two same-key attempts is 1 | **4** |
| `test_alias_spelling_collapses_onto_the_canonical_key_before_uniqueness` | insert `'work'` then `'office'` same day → second rejected; stored value is `office` | 1, 4 |
| `test_unknown_slug_is_stored_and_captured_not_dropped` | row written with the normalised slug; `occasion_unknown_tags` has it with `sample_source='wardrobe_item_wears'` | **1** |
| `test_malformed_slug_is_normalised_not_rejected` | `'Wedding Guest!!'` → `wedding_guest`, write succeeds | 1 |
| `test_all_punctuation_slug_becomes_null` | `'!!!'` → `NULL`, no CHECK violation | 1 |
| `test_occasion_key_shape_check_rejects_an_empty_string_written_by_service_role` | `''` cannot create a second unknown bucket | 1 |
| `test_deleting_an_outfit_nulls_outfit_id_and_leaves_the_wear_row` | row survives, `outfit_id IS NULL` | **2** |
| `test_deleting_an_outfit_does_not_change_wear_count_or_cost_per_wear` | both identical before/after | **2, 5** |
| `test_outfit_fk_rejects_an_outfit_belonging_to_another_user` | `23503` — the composite FK's defence-in-depth | — |
| `test_wear_recency_reports_last_worn_overall_and_for_the_occasion_distinctly` | two wears, different occasions → the two dates differ | **6** |
| `test_wear_recency_never_matches_a_null_occasion_row` | a `NULL`-occasion wear yields `last_worn_on_for_occasion IS NULL`, `wears_for_occasion = 0` | **7** |
| `test_wear_recency_with_a_null_occasion_argument_matches_nothing` | `p_occasion_key => NULL` returns 0 matches for every item | 7 |
| `test_wear_recency_is_rls_scoped_and_not_security_definer` | `prosecdef` is false; a second user's rows are invisible | — |
| `test_normalisation_trigger_is_security_definer_with_a_pinned_search_path` | mirrors `test_normalisation_functions_are_security_definer_with_a_pinned_search_path` | 1 |
| `test_new_indexes_exist_and_the_outfit_one_is_partial` | both names; `idx_item_wears_outfit_id` has a predicate | — |
| `test_outfits_id_user_id_unique_constraint_exists` | prerequisite landed | 2 |
| `test_new_columns_and_constraint_carry_comments` | the three `COMMENT`s from §3.9 exist and are non-empty | — |
| `test_wear_stats_trigger_still_recomputes_after_the_widening` | insert/delete a wear → `wear_count`, `last_worn_at`, `cost_per_wear` all follow | **5** |

**This module is `skipif`-guarded on a live `SUPABASE_DB_URL` + `psycopg2` (`BL-005`), so all of these skip in CI.** QA must say so plainly and run §8 instead of reporting a skip as a pass.

### 7.2 `backend/tests/test_wear_history_repository.py` (new)

Fake `AsyncClient` builder, same style as `test_occasion_repository.py` / `test_app_config_repository.py`.

| Test | Asserts |
|---|---|
| `test_uses_anon_key_with_the_callers_jwt_not_service_role` | pins §5.4's RLS-scoped posture against a later "optimisation" |
| `test_calls_the_wear_recency_rpc_with_both_parameters` | `p_user_id` and `p_occasion_key` are both sent, including when the occasion is `None` |
| `test_maps_every_field_including_null_dates` | `WearRecency` fields, `None` for missing dates |
| `test_returns_empty_list_on_db_error_and_never_raises` | the never-raises contract |
| `test_returns_empty_list_for_a_user_with_no_wears` | empty is not an error |
| `test_wears_for_occasion_is_zero_not_none_when_absent` | the count is always an int, so a caller cannot `None`-arithmetic it |

### 7.3 Boundary sweep (`docs/OPERATOR_RULEBOOK.md` self-attack, folded into §7.1/§7.2)

Empty (`''`, whitespace-only, all-punctuation occasion) · max (a 200-char slug — normalises, no length cap exists on `occasion_key`; assert it is stored rather than truncated) · duplicate (§7.1's three duplicate tests) · concurrent (two same-key inserts in overlapping transactions → one succeeds, one gets `23505`; the constraint, not application logic, is the arbiter — no read-then-write is introduced, so `BL-066`/`BL-036` gain no third instance) · stale (a wear row carrying a slug that has since been deleted from `occasions` still reads back and still renders).

### 7.4 Mobile (Jest + RNTL)

`mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` (modify):

| Test | Asserts | AC |
|---|---|---|
| `logs a wear with a normalised occasion key` | `'Work'` → `office` in the upsert payload | 1 |
| `passes an unknown slug through rather than dropping it` | `sangeet` reaches the payload unchanged | 1 |
| `omits the occasion (null) when none is selected` | `occasion_key: null`, not `''` | 7 |
| `uses the three-column conflict target` | `onConflict: 'item_id,worn_on,occasion_key'` — a structural guard against the target being reverted | 4 |
| `reports alreadyLogged when the upsert returns no rows` | existing behaviour preserved under the widened key | 4 |
| `updates a wear's occasion` | `update({ worn_on, occasion_key })` | 1 |

`mobile/__tests__/features/wardrobe/components/WearOccasionField.test.tsx` (new): renders registry options with labels and badge colours (never raw slugs); includes a "No occasion" chip that clears the selection; re-tapping the selected chip clears it; an unknown/deactivated current value renders (humanised, neutral, selected) via the union rule; taxonomy loading renders a disabled state; taxonomy error renders `WEAR_OCCASIONS_UNAVAILABLE_MESSAGE` and still allows submitting without an occasion.

`mobile/__tests__/features/wardrobe/components/WearHistorySection.test.tsx` (modify): a wear with an occasion renders its label as a coloured badge; a `NULL`-occasion wear renders `WEAR_OCCASION_NONE_CHIP_LABEL` as neutral caption, not a badge; adding a wear passes the selected occasion to the mutation; editing a wear to a date+occasion that already exists renders `WEAR_DUPLICATE_DATE_OCCASION_MESSAGE`; editing with no occasion selected still renders `WEAR_DUPLICATE_DATE_MESSAGE`; the existing loading/error/empty assertions still pass.

---

## 8. Manual / live verification QA must perform

1. **Verify the live PostgreSQL major version first — before writing or pushing any DDL** (§9 Q1). `SELECT current_setting('server_version_num'), version();` against `mefpfykuinasgkpfhmzk` (via the connection `supabase migration list --linked` uses, or the dashboard's Database → Settings). Record the value and the date in the migration header per `docs/OPERATOR_RULEBOOK.md` §E. If it is `<15`, **stop** and take §3.8 to the operator.
2. **Confirm `outfits` is empty and has no `user_id IS NULL` rows** (`SELECT count(*), count(*) FILTER (WHERE user_id IS NULL) FROM outfits;`) before adding `outfits_id_user_id_key`. A `NULL`-owner row is not a blocker (the constraint still applies) but it would be permanently unreferenceable, which is worth knowing.
3. **Serialize the push** (`BL-110`). Confirm with the operator that no sibling Wave 1.5 worktree (SS-034 `014`, SS-036 `016`) is mid-`supabase db push`. Code work stays parallel; the push does not. Then `supabase db push`, then `supabase db diff --linked` — expect siblings' objects as drift, **report the exact diff, never loosen the CI filter** (`BL-060`).
4. **Verify the `ON CONFLICT` arbiter empirically** (§5.2, edge case 12). From the mobile client (or an equivalent PostgREST call), log the same item/date/`NULL`-occasion twice and confirm the second returns **zero inserted rows and creates no second row** — not merely that it did not error. Then repeat with the same non-null occasion. If a duplicate appears, switch to §5.2's RPC and re-run.
5. **Run `backend/scripts/ss035_verify_wear_occasion.py`** (same shape as `ss015_verify_wear_history.py`: `httpx.Client`, `admin_headers()`/`user_headers()`, a `check()` accumulator, throwaway users torn down at the end). It must cover, live:
   - the AC #5 before/after fixture on a real item with a `purchase_price` — `wear_count`, `last_worn_at`, `cost_per_wear` identical either side of the migration (the migration's own guard proves it too, but this proves it from outside);
   - office-morning + puja-evening on one date → two rows, `wear_count = 2` (the §9 Q2 semantic, observed rather than assumed);
   - repeat same-occasion tap → no new row, `wear_count` unchanged;
   - two `NULL`-occasion taps on one date → second rejected, `wear_count` unchanged;
   - `'Work'` then `'office'` on one date → second rejected, stored value is `office`;
   - an unknown slug → row written, `occasion_unknown_tags` row present with `sample_source='wardrobe_item_wears'`;
   - create an outfit as user A, attach it to a wear, delete the outfit → wear row survives with `outfit_id IS NULL`, `wear_count` and `cost_per_wear` byte-identical;
   - user A's `wear_recency` RPC returns A's items only; user B's returns zero rows for A's items (RLS, verified rather than asserted);
   - a wear row referencing user B's outfit is rejected (`23503`).
6. **Regenerate `mobile/types/supabase.ts` after the push**, and commit **only if** the diff is confined to this ticket's objects (§9 Q4). The mobile changes do not typecheck until this happens, so do it before running `npx tsc --noEmit` and Jest, and say in the worklog which way it went.
7. **Re-verify SS-015's shipped behaviour end-to-end in the app**: Mark Worn one-tap still logs today with no occasion and shows the cost-per-wear toast; wear history still lists, edits and deletes; `wear_count`/`cost_per_wear` still follow. The widened constraint sits under all of it.

---

## 9. Open questions / blockers

**Q1 — The live project's PostgreSQL major version is UNVERIFIED, and two statements in this migration depend on it. This is the one hard precondition.** `supabase/config.toml:42` declares `major_version = 17`, and the CLI's own comment on that line says it "has to be the same as your remote database's" — but that is a **local-stack declaration whose accuracy nobody has checked against the remote**, and the raw ticket records that an MCP query against `mefpfykuinasgkpfhmzk` was permission-denied on 2026-07-30. `[VERIFIED 2026-08-04 — `config.toml:42` says 17; this is the local stack's configured version only.]` `[UNVERIFIED — the remote server's `server_version_num`. This Architect pass has no Bash, no psql and no dashboard access and therefore **cannot** verify it; I am not going to assert it from the config file, which is exactly the `BL-001` failure mode.]` **Developer must run §8 step 1 before writing DDL.** The migration's own version gate (§3.1) turns a wrong assumption into a loud first-statement failure rather than a partial apply, and §3.8 documents the `<15` fallback — but taking that fallback changes the client write path (RPC becomes mandatory) and is a scope change that needs the operator's sign-off, not the Developer's judgement.

**Q2 — `wear_count` semantics change, and it moves a money figure. Needs a product decision at this gate.** The stats trigger is `COUNT(*)` (`006:55`), so once two occasions may share a date, an item worn to office in the morning and a puja in the evening counts **2**, and `cost_per_wear = purchase_price / wear_count` **halves** for that day's contribution. Before this ticket, one calendar day could contribute at most 1. This design **keeps `COUNT(*)`**, because (a) the user's 2026-07-30 decision asserts the garment genuinely was worn twice, (b) "one row = one wear" is SS-015's existing semantic and the one-per-day constraint was always an *idempotency* device rather than a claim about physics, and (c) `COUNT(DISTINCT worn_on)` would make the visible wear-history list and the displayed `Worn N×` disagree, which is its own silent-confusion bug. The alternative is one line in `sync_wardrobe_item_wear_stats`. **Confirm or overrule before Developer starts** — this is `BL-075`'s money-unit class and the ticket's own Technical Notes flag "a double-counted wear silently halves a money figure" as the expensive failure here. Note the direction of the change is *toward* a lower cost-per-wear, i.e. flattering, which makes it less likely to be noticed.

**Q3 — Occasion selection is optional, which may starve the signal this ticket exists to create.** The ticket's Technical Notes require that a user who just taps "worn" gets `NULL`, so the primary `ItemDetailSheet` button stays one tap and the picker lives in the Wear history sheet (§5.3). The honest consequence: if most wears are logged by the quick tap, `occasion_key` is mostly `NULL`, `wear_recency` returns "never worn for this occasion" for nearly everything, and occasion-aware novelty degrades to global novelty — a real feature that quietly does nothing. Options if product wants more coverage: an occasion chip row inside the wear-logged toast ("logged — was this for…?"), or defaulting the occasion from the suggestion session that produced the outfit once SS-020 exists. **Not resolved here** (either would exceed this ticket's AC list); logged as `BL-119`.

**Q4 — Regenerating `mobile/types/supabase.ts` collides with the parallel worktrees, but this ticket cannot skip it.** `supabase gen types` reads the *live* database, which after a serialized Wave 1.5 push also contains SS-034's and SS-036's objects (`BL-110`). SS-033 §9 Q3's directive was "commit only if the diff is confined to this ticket's objects; otherwise leave it and let the last ticket to merge regenerate once." **That directive is harder here**: unlike SS-033, this ticket has mobile code that *reads* the new columns through `Tables<'wardrobe_item_wears'>`, so an unregenerated file means `mobile/` does not typecheck. If the diff is not confinable, the Developer must say so explicitly and the operator decides between (a) committing a types file that includes siblings' tables, or (b) holding this ticket's mobile half until the siblings merge. Do not resolve this by hand-editing the generated file (CLAUDE.md forbids it) or by adding a local interface for the row type.

**Q5 — Nothing consumes `wear_recency()` when this ticket merges.** By design (§2.3, `BL-096`). The consequence worth stating: occasion-aware novelty does not exist until Engine v2 / SS-020 wires it, and unlike impressions this data *is* retroactively useful once collected, so the ordering is less urgent than SS-033's — but a read function with no reader is dead surface if nobody owns it. `BL-117`.

**Q6 — No conflict found between the ACs and CLAUDE.md**, with one deviation from the raw ticket recorded openly: the ticket's edge-case line "`ON DELETE RESTRICT` on the registry side, consistent with `occasions.parent_key`" is not implementable alongside its own AC #1 and is resolved as "no foreign key" in §3.4, which delivers the same intent more strongly. Called out here rather than slipped in.

---

## 10. Backlog deltas

> Applied by the operator to the main checkout's `docs/BACKLOG.md` — this Architect pass has no `Edit` tool and `BACKLOG.md` is shared repo state that must not be written from a worktree. **ID hazard:** `BL-115` is the highest ID in this worktree's copy, so new rows start at **`BL-116`** — but SS-034 and SS-036 are appending from the same baseline, so reconcile before applying (the `BL-097`–`BL-106` collision documented in the file's ID-reservation notice is the precedent).

**Active-table resurfacing scan** (tags `schema`/`infra`/`ci`/`test`/`ai`, per the orchestrator's hand-off plus my own grep):

- **`BL-071`** (schema, Active) — **honoured, not regressed; and the Active copy is stale bookkeeping.** This row already appears a second time in the **Resolved** table (`BACKLOG.md:139`, "Resolved by SS-015 / Architect"); the Active copy at `:51` should have been moved, not duplicated. **Recommend deleting the stale Active copy** (the Resolved entry is the audit trail). Substantively: SS-035 preserves the guarantee under a widened constraint via `NULLS NOT DISTINCT` (§3.3), adds three explicit regression tests (§7.1), introduces **no** new client-writable derived cache, and leaves `wear_count`/`last_worn_at` trigger-maintained and untouched. One note to carry forward: `wear_count` now counts *occasion-distinct* wears, so a two-occasion day counts 2 — §9 Q2.
- **`BL-078`** (schema, Active) — **stays Active** (it is a standing obligation by definition, and SS-025's own note says so). Note to append: SS-035 adds **boundary 7**, `wardrobe_item_wears.occasion_key`, to SS-025 §6.4's matrix. **Decision: it gets both halves.** A DB-level `BEFORE INSERT OR UPDATE` `SECURITY DEFINER` backstop (`wear_occasion_key_normalize_trigger`, a *new* function — `008`'s `occasion_scalar_normalize_trigger` is hardcoded to a column named `occasion` and cannot be reused, and parameterising it would require dynamic SQL inside a privileged function, which `007:166-171` forbids in capitals) **and** application-layer normalisation in `wardrobe.service.ts` reusing the shipped `resolveOccasionKey`. Boundaries 4–6 got trigger-only because no application write path existed; this one has a client write path from day one, so trigger-only would have been the weaker read of the matrix's own rule. This is the first boundary to ship with both from the start.
- **`BL-004`** (schema, **Parked** — note only, row not moved; Parked is `/audit`'s to reconcile). **The row's risk does not extend to this ticket's new columns.** `occasion_key` and `outfit_id` are **user-authored facts, not derived caches** — the user chooses the occasion, so client-writability is correct rather than a gap, and `user_owns_item_wears`' `WITH CHECK` already scopes it. No new `GENERATED`/derived/trigger-maintained column is added. The columns this row does cover (`wear_count`, `last_worn_at`, `cost_per_wear`) keep exactly SS-015's mitigation — no client write path exists (`markWardrobeItemWorn` stays deleted) and the `COMMENT ON COLUMN` markers from `006:105-108` are untouched — and §7.1's `test_wear_stats_trigger_still_recomputes_after_the_widening` pins that the trigger still owns them under the new constraint.
- **`BL-110`** (ci, Active) — stays Active. Note: SS-035 is the **fourth** Wave 1.5 migration against the shared live project (`015`, after `012`/`013`/`014`). §8 step 3 serializes the push and requires reporting the exact `db diff` without loosening the filter; §9 Q4 extends the caution to the generated types file, and notes this ticket is *harder* than SS-033 because its mobile code depends on the regen. Still a convention rather than an enforced mechanism; no CI push-lock is added here.
- **`BL-075`** (schema/money, Active) — stays Active. Note: §9 Q2 is a new instance of this row's class — a schema change that silently moves `cost_per_wear` for multi-occasion days. Surfaced as a sign-off question rather than absorbed.
- **`BL-060`** (ci, Active) — stays Active, note added: this ticket's `db diff` will show sibling objects; the standing directive not to loosen the filter is restated in §8 step 3.
- **`BL-005`** (test, Parked — note only) — this ticket's most safety-relevant assertions (the `NULLS NOT DISTINCT` duplicate guards, the `ON DELETE SET NULL (outfit_id)` behaviour, the RLS scoping of `wear_recency`) all live in `test_db_schema.py` and will **skip** in CI. §8's live script is the compensating control; QA must not report a skip as a pass.
- **`BL-096`** (ai, Active) — stays Active, untouched. §2.3 explains why SS-035 stays out of `outfit_suggestion_service.py`; `BL-102`/SS-033 is the precedent.
- **`BL-037`** (infra, Active) — stays Active, does not block. Nothing here needs a deployed backend; the new adapter is exercised by unit tests and by a local script against the live project, the SS-026/SS-033 pattern.

**New rows** (Active unless marked):

- **`BL-116`** (schema, Active) — **the live Supabase project's PostgreSQL major version has never been verified.** `supabase/config.toml:42` declares `major_version = 17`, but that is a local-stack declaration; an MCP query against `mefpfykuinasgkpfhmzk` was permission-denied on 2026-07-30 and this Architect pass had no way to check. SS-035 is the first migration to depend on version-gated syntax (`UNIQUE NULLS NOT DISTINCT`, `ON DELETE SET NULL (column)`, both PG15+), and every future migration inherits the same unknown. Record the verified value somewhere durable once SS-035's Developer obtains it.
- **`BL-117`** (ai, Active) — `public.wear_recency()` and `IWearHistoryRepository` ship with **zero callers**; occasion-aware novelty does not exist until Engine v2 / SS-020 wires them into scoring. Same shape as `BL-114`: substrate with no owner drifts into dead surface. SS-020 / Engine v2 is the natural owner.
- **`BL-118`** (schema, Active) — `wardrobe_item_wears.outfit_id` ships with **no writer**: there is no application write path to `outfits` anywhere in the repo `[VERIFIED 2026-08-04]`, so the column stays `NULL` until SS-020/SS-023 build a "worn this outfit" surface. The FK, its `outfits_id_user_id_key` prerequisite and the partial index are all in place and tested; only the producer is missing.
- **`BL-119`** (ai, Active) — the one-tap "Mark Worn" writes `occasion_key = NULL` by design (the ticket requires occasion selection to be optional), so occasion coverage may stay sparse and occasion-aware novelty may quietly degrade to global novelty. Needs a product decision on whether the primary tap should prompt (toast-level chip row) or default from the suggestion session once SS-020 exists. §9 Q3.
- **`BL-120`** (schema, Parked) — `wardrobe_item_wears` now carries an occasion and an outfit, which makes it the closest thing in the schema to an outcome log, while `suggestion_outcomes.outcome_type = 'worn'` (SS-033) records the same real-world event from the suggestion side. Nothing reconciles the two, and nothing stops one user action producing a `worn` outcome with no wear row or vice versa. Decide the relationship (one writes the other? a join key? deliberately independent?) before SS-020 wires either.

---

**Risk: high — confirmed, not downgraded.** Four independent one-way-door surfaces per `docs/OPERATOR_RULEBOOK.md` §C2. (1) It **replaces a shipped `UNIQUE` constraint** on a live table whose only job is `BL-071`'s idempotency guarantee, and the replacement's correctness rests on a single modifier (`NULLS NOT DISTINCT`) whose omission fails **silently** — duplicates accumulate, no error is raised, and the first symptom is a wrong number. (2) That constraint sits directly upstream of a trigger feeding a **`GENERATED ALWAYS … STORED` money column**, so any miscount silently moves `cost_per_wear`; the ticket additionally changes what `wear_count` *means* for multi-occasion days (§9 Q2), which is a product decision about a money figure, not an implementation detail. (3) It adds a **new occasion write boundary** (`BL-078`) and a new `SECURITY DEFINER` function, plus a **composite FK requiring a new `UNIQUE` constraint on the shipped `outfits` table**, where the obvious implementation of `ON DELETE SET NULL` breaks the ticket's own AC #2 against a `NOT NULL` column. (4) The entire DDL depends on a **live PostgreSQL major version this pass could not verify** (§9 Q1), against a shared project three sibling worktrees are pushing to. Every one of these fails quietly rather than loudly, which is precisely the class the full lane's gates exist to catch.
