# SS-040 — Item Lifecycle & Cost-Per-Wear Schema (trimmed) — Design

Tier: `standard` (Est: 12h) · Architect pass 2026-08-20 (Opus)

## Scope restatement

Add the five `wardrobe_items` columns that genuinely don't exist yet (`do_not_style`, `is_archived`, `condition`, `custom_tags[]`, `render_transform`) in one additive migration, and — the part that carries the ticket — make `do_not_style` and `is_archived` actually change what the suggestion engine can pick, by threading them from the DB select list through `WardrobeItemInput` into `engine_v2_eligibility.filter_eligible`'s exclusion path. The columns SS-052 and SS-055 were going to need for cost-per-wear/insights (`brand`, `purchase_price`, `purchase_date`, `is_favourite`, generated `cost_per_wear`) already exist and are not touched. No UI is in scope: this ticket ships the column + the read path, not a writer.

## Ground-check findings (done before designing — do not re-derive)

Everything below was checked against the repo on 2026-08-20, not taken from the raw ticket's note.

1. **The raw ticket's schema claim is CORRECT.** `001_initial.sql:44-73` defines `wardrobe_items` with `brand` (58), `purchase_price` (59, "in paise"), `purchase_date` (60), `cost_per_wear` (63-68, `GENERATED ALWAYS ... STORED`), `is_favourite` (71). Do not re-add any of them.
2. **No later migration added any of the five target columns.** Every migration 002→022 was grepped for `wardrobe_items`: the only column-shape changes since 001 are `005` (`ALTER COLUMN category DROP NOT NULL` + `ADD COLUMN processing_status`, + adds the table to the `supabase_realtime` publication), `006` (`ADD CONSTRAINT wardrobe_items_id_user_id_key UNIQUE (id, user_id)`), and `008` (`occasion_tags` → `TEXT[]`). A repo-wide grep for `do_not_style|is_archived|custom_tags|render_transform` in `supabase/` returns **zero** hits. The gap is exactly the five columns named.
3. **Next free migration number is `023`.** `022_garment_category_resolution.sql` (SS-044) is the highest present.
4. **RLS: `001_initial.sql:164-165` is `CREATE POLICY "user_owns_wardrobe" ON wardrobe_items FOR ALL USING (auth.uid() = user_id)`, with RLS enabled at line 152.** Postgres RLS is row-level: a policy grants/denies whole rows, so new columns on an existing row are covered by the existing policy with no policy change. (Note the policy has no explicit `WITH CHECK`; for a `FOR ALL` policy Postgres applies the `USING` expression as the check on INSERT/UPDATE — `[trained-knowledge, not verified this session]`, and unchanged by this ticket either way.) **No RLS change in this migration.**
5. **The wiring chain is four files long, and the raw ticket only names two of them.** `WardrobeRepository.get_items_for_styling` (`backend/adapters/wardrobe_repository.py:179-191`) selects an **explicit column list** — `"id, category, color_primary, color_secondary, pattern, fabric, occasion_tags, season_tags, wear_count, last_worn_at"`. That list feeds `OutfitPortfolioService._fetch_wardrobe` (`backend/services/outfit_portfolio_service.py:312-325`), which does `WardrobeItemInput.model_validate(row)` and **silently skips any row that fails validation** (logs `outfit_portfolio_wardrobe_row_skipped`, `continue`), then `EngineV2.generate_portfolio` (`engine_v2.py:202-204`) calls `filter_eligible`. **Adding fields to `WardrobeItemInput` alone does nothing** — the select list and the port docstring at `backend/adapters/interfaces.py:602-613` (which enumerates the columns verbatim) must both be extended or the new fields arrive as their defaults forever.
6. **`filter_eligible` (`engine_v2_eligibility.py:93-176`) is pure and has a clean insertion point**, as the ticket claims: `_dedupe_by_id` → `excluded_missing` count + `missing_filtered` → white/hard-family filter → `pre_weather` → optional weather branch with a relax-if-empty fallback to `pre_weather`.
7. **Every UPDATE to a `wardrobe_items` row fires `trg_wardrobe_items_normalize_occasions` (`008_occasion_columns_to_text.sql:75-77`), which has NO `WHEN` clause.** So a future "toggle do-not-style" write re-runs occasion normalisation and can re-`occasion_log_unknown`, inflating `occasion_unknown_tags.occurrences` — this is exactly `BL-124`, and these columns add a new high-frequency UPDATE path that will amplify it. (`016`'s pattern/fabric trigger is guarded by `WHEN (NEW.pattern IS DISTINCT FROM OLD.pattern OR NEW.fabric IS DISTINCT FROM OLD.fabric)` and will **not** fire on a lifecycle-flag toggle.)
8. **Mobile reads `wardrobe_items` with `.select('*')`** (`mobile/features/wardrobe/wardrobe.service.ts:333-334`, `399`), so new columns flow to the client automatically once `mobile/types/supabase.ts` is regenerated. `mobile/types/supabase.ts` currently has `wardrobe_items` at line 1132 with `is_favourite` present, and **no `suggestion_narration_cache` entry — `BL-143`'s staleness is confirmed still live** and is closable by this ticket's regeneration step.
9. **Live-DB schema tests are skip-gated.** `backend/tests/test_db_schema.py:45-59` is `importorskip("psycopg2")` + `skipif(not SUPABASE_DB_URL)`, so schema assertions there are **not** a CI gate. The enforcing tests for this ticket must be pure-Python (eligibility, repository select list) plus a filesystem grep test.

## Files to create/modify

**Create**

| Path | What |
|---|---|
| `supabase/migrations/023_item_lifecycle_columns.sql` | The additive migration (five columns + GIN index + column comments + rollback block, following `022`'s header/rollback comment style). |
| `backend/tests/test_engine_v2_eligibility_lifecycle.py` | The AC-enforcing exclusion tests (sibling of the existing `test_engine_v2_eligibility.py` / `test_engine_v2_eligibility_weather.py` split). |
| `backend/tests/test_render_transform_purely_additive.py` | Grep-based "nothing reads `render_transform` yet" guard, modelled on `backend/tests/test_garment_registry_purely_additive.py` (pure filesystem, no live DB, must run in every CI invocation). |

**Modify**

| Path | What |
|---|---|
| `backend/services/styling_rules_types.py` | `WardrobeItemInput` gains `do_not_style`, `is_archived`, `condition`, `custom_tags`. **Not** `render_transform` — the engine has no use for it and SS-055 owns its shape. |
| `backend/services/engine_v2_eligibility.py` | Lifecycle exclusion inside `filter_eligible`, immediately after `_dedupe_by_id`. |
| `backend/services/engine_v2_types.py` | `EligibilityResult` gains `excluded_lifecycle: int = 0` (additive, defaulted). |
| `backend/adapters/wardrobe_repository.py` | `get_items_for_styling`'s explicit select list gains the four columns. |
| `backend/adapters/interfaces.py` | `IWardrobeRepository.get_items_for_styling` docstring (602-613) enumerates the columns verbatim — update it, don't leave it stale. |
| `backend/tests/test_wardrobe_repository.py` | Assert the new columns are in the select string (the fake client already records `select` args — see the `test_get_item_image_info_selects_thumbnail_url_too` pattern at :366-390). |
| `backend/tests/test_outfit_portfolio_service.py` | One test that a repo row carrying the new keys survives `_fetch_wardrobe`'s `model_validate` and arrives at the engine with the flags set. |
| `backend/tests/test_db_schema.py` | Live-gated assertions for the five columns + the `custom_tags` GIN index (documented as skip-gated, not a CI gate). |
| `mobile/types/supabase.ts` | Regenerate (full regeneration — this also closes `BL-143`; see Open Questions). |

**Explicitly NOT modified:** `backend/services/engine_v2.py` (it forwards `EligibilityResult` fields it already knows about; the new counter stays internal — see below), `styling_rules_types.GapReport`, any mobile feature code, any RLS policy.

## Concrete values to use, not invent

### Migration `023_item_lifecycle_columns.sql`

```sql
ALTER TABLE wardrobe_items
  ADD COLUMN IF NOT EXISTS do_not_style     BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_archived      BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS condition        TEXT,
  ADD COLUMN IF NOT EXISTS custom_tags      TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS render_transform JSONB;

CREATE INDEX IF NOT EXISTS idx_wardrobe_custom_tags
  ON wardrobe_items USING GIN(custom_tags);
```

Fixed decisions behind those exact lines:

- **`NOT NULL DEFAULT false` on the two booleans and `NOT NULL DEFAULT '{}'` on `custom_tags`, not bare nullable.** The AC says "nullable/defaulted"; defaulted-and-NOT-NULL satisfies it and is strictly safer here, because a NULL boolean reaching `WardrobeItemInput` would fail `bool` validation and `_fetch_wardrobe` would then **silently drop that item from the user's wardrobe** (finding 5). Removing the possibility at the column is better than catching it downstream. `[trained-knowledge, not verified this session]` PostgreSQL 11+ implements `ADD COLUMN ... NOT NULL DEFAULT <constant>` as a metadata-only "fast default" with no table rewrite, so this does not rewrite existing rows. Developer: if the live push on the linked project is anything other than instantaneous, stop and fall back to plain `DEFAULT false` (nullable) plus the lenient-parse mitigation below — do not sit on a long `ACCESS EXCLUSIVE` lock.
- **`condition TEXT` with no CHECK constraint.** No controlled vocabulary for it exists anywhere in this repo, and inventing one here would be the same mistake `BL-064` already records for `pattern`/`fabric`. Ships as free text; vocabulary is a backlog item (`BL-195`, below).
- **`render_transform JSONB`, nullable, no CHECK, no default.** Per the ticket's Technical Notes: `SS-055` owns the `{x, y, scale, rotation, z}` shape. Do not add a CHECK, a default `'{}'`, or a comment that asserts a shape.
- **GIN index named `idx_wardrobe_custom_tags`**, mirroring `001_initial.sql:77`'s `idx_wardrobe_occasions ON wardrobe_items USING GIN(occasion_tags)`.
- **`IF NOT EXISTS` on every statement** — this repo's migrations are re-runnable against a linked project shared by parallel worktrees (`BL-002`, `BL-110`).
- **Add `COMMENT ON COLUMN` for `do_not_style`, `is_archived` and `render_transform`** stating who reads them (`engine_v2_eligibility`; `SS-055` for the transform), following `006_wardrobe_item_wears.sql:105-108`'s precedent. Include a commented-out `ROLLBACK` block like `016`/`008` do.
- **No RLS statement in this migration**, and a header comment saying why (finding 4): row-level policy, new columns inherit it, `user_owns_wardrobe` unchanged.

### `WardrobeItemInput` additions (`backend/services/styling_rules_types.py`)

Appended after `last_worn_at`, existing fields untouched:

```python
    # (SS-040) Lifecycle flags, read by engine_v2_eligibility.filter_eligible.
    # Optional-with-False-default: migration 023 declares both NOT NULL
    # DEFAULT false, but a caller/fixture omitting them, or a PostgREST
    # select list that forgets them, must degrade to "stylable" rather than
    # drop the item (outfit_portfolio_service._fetch_wardrobe skips rows
    # that fail validation).
    do_not_style: bool = False
    is_archived: bool = False
    condition: str | None = None
    custom_tags: list[str] = Field(default_factory=list)
```

`custom_tags` mirrors `occasion_tags`' `Field(default_factory=list)` exactly. Values are stored and read **verbatim** — no casefolding, no dedupe, no normalisation (ticket edge case; that's `BL-064`'s problem).

### `EligibilityResult` addition (`backend/services/engine_v2_types.py`)

```python
    # (SS-040) Count of DISTINCT items removed by the do_not_style/is_archived
    # lifecycle filter. An item with both flags set counts ONCE.
    excluded_lifecycle: int = 0
```

Additive with a default, same posture as SS-022's `weather_exclusions_relaxed: bool = False`.

### The exclusion itself (`engine_v2_eligibility.filter_eligible`)

Insert between `deduped = _dedupe_by_id(wardrobe)` (line 115) and the `excluded_missing` count (line 117):

```python
    stylable = [item for item in deduped if not (item.do_not_style or item.is_archived)]
    excluded_lifecycle = len(deduped) - len(stylable)
```

then every downstream use of `deduped` (the `excluded_missing` count and `missing_filtered`) reads `stylable` instead, and `excluded_lifecycle` is passed to `EligibilityResult`.

Four ordering/semantics decisions that are load-bearing, stated so the Developer doesn't have to choose:

1. **Lifecycle filter runs FIRST, before the missing-category/colour count.** An archived item that also lacks a category must not be counted in `excluded_missing_color_or_category` — otherwise the gap report tells the user "3 items aren't tagged yet" about items they deliberately archived. This is what makes the ticket's "excluded once, not double-counted" edge case true by construction rather than by a special case.
2. **One predicate, `not (do_not_style or is_archived)` — a single boolean OR, not two sequential filters.** An item with both flags is removed once and counted once in `excluded_lifecycle`.
3. **Lifecycle exclusions are NEVER relaxed.** `pre_weather` is derived from the lifecycle-filtered pool, so the SS-022 relax-if-empty guardrail (lines 164-170) falls back to `pre_weather` — which is already lifecycle-filtered. A do-not-style item must not reappear because the user's wardrobe is otherwise all white and it's raining. Weather exclusions are the engine's inference; `do_not_style` is the user's explicit instruction, and the user wins. Assert this with a test.
4. **`excluded_lifecycle` stops at `EligibilityResult`; `GapReport` and the API response are unchanged.** The AC doesn't ask for user-facing reporting, and widening `GapReport` widens the suggestion API's response contract, which is a separate decision with a UI owner. Logged as `BL-196` rather than silently picked.

### Runtime-behaviour claim this design makes

With migration `023` applied and every existing row therefore at `do_not_style = false, is_archived = false`, `filter_eligible` returns byte-identical output to today for every existing user: `stylable == deduped`, `excluded_lifecycle == 0`. The engine's behaviour changes only once something writes `true` — and nothing does yet (see Open Questions). This is the same "additive, inert until a writer exists" posture SS-034 shipped.

## Edge cases

Carried forward from the ticket:

- **`do_not_style = true` on an item already inside a saved outfit (`outfits.item_ids`).** No cascade, no re-validation, no rewrite of `outfits` or `outfits.items_snapshot` (migration `020`). The flag only gates *future* suggestion assembly. The migration touches no other table; assert nothing in `outfits` is read or written by this ticket.
- **Both flags set on one item.** Excluded once, `excluded_lifecycle` increments by one — guaranteed by the single-OR predicate above, asserted by a test.
- **`custom_tags` with near-duplicate strings (`"office"` vs `"Office"`).** Stored verbatim, no normalisation, no dedupe, no CHECK. Explicitly out of scope (`BL-064`).
- **NULL `render_transform` must break no existing reader.** Nothing reads it; the grep test locks that in so SS-055 inherits a clean start.

New, found during the ground-check:

- **A NULL/absent lifecycle flag must not delete an item from the user's wardrobe.** `_fetch_wardrobe` skips any row failing `model_validate` (`outfit_portfolio_service.py:316-323`). Belt (column `NOT NULL DEFAULT false`) and braces (pydantic default `False`) — and a test that a row dict *missing* both keys still validates and stays eligible.
- **`get_items_for_styling`'s explicit select list is the actual single point of failure for this AC.** If the columns are added everywhere except that string, every item silently arrives with `do_not_style = False` and the feature is a no-op that all unit tests still pass. This is why the repository select-list test is mandatory, not optional.
- **Toggling a lifecycle flag fires `trg_wardrobe_items_normalize_occasions` on every UPDATE (no `WHEN` clause, finding 7)**, re-running occasion normalisation and potentially re-logging unknown occasion tags — `BL-124`, amplified by this ticket's new write path. Not fixed here (fixing it means altering a shipped trigger, which is out of this ticket's additive scope); flagged so whoever builds the toggle UI knows.
- **`outfit_outcome_service._build_items_snapshot` also calls `get_items_for_styling`** (`:153`) and reads only `category`/`color_primary` from each row via `.get()`. Widening the select list is safe for it — extra keys are ignored — but the Developer must not "tidy" that call into a narrower shared query.
- **Second engine caller check:** `filter_eligible` has exactly one production call site (`engine_v2.py:202`). No other service assembles an eligible pool that would need the same filter — but `SS-048`'s rails and `SS-052`'s insights will (see Open Questions).
- **Parallel-worktree drift.** Pushing `023` from a worktree while another ticket's objects exist on the shared linked project makes `supabase db diff --linked` non-empty for reasons unrelated to this migration (`BL-110`). Interpret a non-empty diff against that known noise before treating it as a failure.

## Test plan

Every test below is pure-Python/filesystem and runs in CI without a database. The live-DB ones are additive and skip-gated.

**`backend/tests/test_engine_v2_eligibility_lifecycle.py`** (new — the AC's "asserted by a test")

- `test_do_not_style_item_is_excluded_from_eligible_pool` — a 3-item wardrobe with one `do_not_style=True`; asserts that id is absent from `result.eligible_items` and the other two are present.
- `test_is_archived_item_is_excluded_from_eligible_pool` — same shape for `is_archived=True`.
- `test_item_with_both_flags_is_counted_once` — one item, both flags; asserts `excluded_lifecycle == 1` (not 2) and the pool is empty.
- `test_excluded_lifecycle_counts_distinct_items` — two flagged items of a five-item wardrobe; asserts `excluded_lifecycle == 2` and `len(eligible_items) == 3`.
- `test_archived_item_missing_category_is_not_also_counted_as_missing` — one item with `is_archived=True` **and** `category=None`; asserts `excluded_lifecycle == 1` **and** `excluded_missing_color_or_category == 0` (the ordering decision, made falsifiable).
- `test_lifecycle_exclusions_are_not_relaxed_when_pool_empties_under_weather` — every non-flagged item is white/silk under `WeatherContext(is_heavy_rain=True)` so the relax path triggers; asserts the `do_not_style` item is **still** absent from `eligible_items` while `weather_exclusions_relaxed is True`.
- `test_default_wardrobe_item_input_is_stylable` — `WardrobeItemInput(id="x", category=..., color_primary=...)` with neither flag supplied; asserts it survives into `eligible_items` and `excluded_lifecycle == 0` (byte-identical-to-today guarantee).
- `test_row_dict_without_lifecycle_keys_validates` — `WardrobeItemInput.model_validate({...})` on a dict with no `do_not_style`/`is_archived`/`custom_tags` keys; asserts no exception and `do_not_style is False`, `custom_tags == []`.
- `test_custom_tags_are_stored_verbatim` — `["office", "Office", " office "]` round-trips unchanged through `WardrobeItemInput` (no casefold/strip/dedupe).

**`backend/tests/test_wardrobe_repository.py`** (extend)

- `test_get_items_for_styling_selects_lifecycle_columns` — drives the existing fake client, pulls the recorded `select` call args, asserts `do_not_style`, `is_archived`, `condition`, `custom_tags` all appear in the select string (mirrors `test_get_item_image_info_selects_thumbnail_url_too` at :366-390). This is the test that stops the whole feature being a silent no-op.

**`backend/tests/test_outfit_portfolio_service.py`** (extend)

- `test_fetch_wardrobe_preserves_lifecycle_flags` — the fake repo returns a row with `do_not_style: True`; asserts the `WardrobeItemInput` handed to the engine has `do_not_style is True` (i.e. the row is not skipped and the flag is not dropped in transit).

**`backend/tests/test_render_transform_purely_additive.py`** (new — SS-034 pattern)

- `test_render_transform_has_no_backend_or_mobile_readers` — greps `backend/` and `mobile/` sources (excluding `tests/`, `scripts/`, `docs/`, `supabase/migrations/`, and `mobile/types/supabase.ts`, which is generated) for `render_transform`; asserts zero hits, with a docstring naming `SS-055` as the ticket that will legitimately break this test and telling that Architect to narrow it rather than delete it.
- `test_render_transform_column_exists_in_migration_023` — cross-checks the identifier against the migration file itself, so a rename fails this test loudly instead of the grep silently checking a stale name forever (the exact guard `test_garment_registry_purely_additive.py` already uses).

**`backend/tests/test_db_schema.py`** (extend, skip-gated — documentation-grade, not a CI gate)

- `test_wardrobe_items_has_lifecycle_columns` — `information_schema.columns` shows all five with the expected `data_type`/`is_nullable`/`column_default`.
- `test_custom_tags_gin_index_exists` — `pg_indexes` contains `idx_wardrobe_custom_tags`, mirroring the file's existing `occasion_tags` GIN assertion.
- `test_rls_still_denies_cross_user_read_of_new_columns` — extends the module's existing `SET ROLE authenticated` cross-user read test to select `do_not_style, custom_tags` and assert zero rows, turning AC #5 into an executable claim rather than a paragraph.

**Regression bar:** the existing `test_engine_v2_eligibility.py`, `test_engine_v2_eligibility_weather.py`, `test_engine_v2_integration.py` and `test_engine_v2_properties.py` must pass **unchanged**. If any of them needs editing, the change was not additive — stop and re-read decision (1).

## Open questions / blockers

None of these block the Developer from starting. Ranked by what could actually bite.

1. **Nothing writes these columns. There is no UI, endpoint, or service that can set `do_not_style = true`.** The competitive epics doc (`07-EPICS-AND-TICKETS.md:43-45`) names only readers — `SS-052` (insights, excludes archived/do-not-style from metrics), `SS-055` (`render_transform`), `SS-048` (rails must exclude both). The ticket ships a correctly-wired *read* path that is 100% live-inert until a writer exists, which is fine and intended — but it should be stated, not discovered later, and the writer needs an owner. Logged as **`BL-194`**.
2. **`custom_tags` and `condition` have no consumer at all** — not even a reader. They are here because `SS-052`/`SS-057` were assumed to want them. They ship as pure columns; no code path in this ticket touches them beyond the pydantic field and the GIN index. If the user would rather not ship unconsumed columns, dropping `condition` and `custom_tags` from this migration costs nothing and is reversible in a way that removing them later isn't.
3. **`condition` has no controlled vocabulary** (free `TEXT`, same shape as the `pattern`/`fabric` problem `BL-064` already records). Logged as **`BL-195`** rather than inventing an enum here.
4. **Lifecycle exclusions are invisible to the user.** A user who archives most of their wardrobe gets fewer or zero suggestions with no explanation, because `excluded_lifecycle` deliberately stops at `EligibilityResult` (decision 4). Logged as **`BL-196`**.
5. **`BL-124` is amplified by this ticket** (finding 7): the un-guarded `trg_wardrobe_items_normalize_occasions` fires on every lifecycle-flag UPDATE. Not fixed here — fixing it means altering a shipped trigger, which is neither additive nor this ticket's AC. Existing row stays open; noted on it via this design doc rather than duplicated.
6. **`BL-143` is closable by this ticket's regeneration step.** `mobile/types/supabase.ts` is confirmed still missing `suggestion_narration_cache`/`purge_suggestion_narration_cache` (finding 8). AC #6 requires regenerating that file anyway — a genuine full regeneration picks those up for free. Developer: regenerate the whole file (don't hand-patch the `wardrobe_items` block), then confirm `suggestion_narration_cache` is present and move `BL-143` to Resolved. Left Active for now because it isn't resolved until that regeneration actually happens.
7. **`supabase db diff --linked` cannot be run in CI** — `BL-028` (no local Docker Supabase) and `BL-110` (parallel worktrees make the shared linked project look drifted) are both still open, and every prior migration ticket hit this. AC #7 is therefore satisfiable only as a manual, operator-run check against the linked project, reported honestly as such in the worklog. Do not claim a clean diff that wasn't observed.
8. **`BL-075` (money-unit ambiguity: `purchase_price` commented "in paise", treated as rupees by shipped UI) stays open and is NOT resolved here.** This ticket adds no money column and changes no money code — but `SS-052` reads the `GENERATED cost_per_wear` built on `purchase_price`, so this must be settled before insights ship, not by this ticket. Explicitly re-deferred rather than silently skipped.
9. **`condition`'s name is a Postgres non-reserved keyword.** Unquoted `condition` as a column name is legal in PostgreSQL `[trained-knowledge, not verified this session]`, and PostgREST/`supabase-py` quote identifiers, so no conflict is expected. If the migration errors, quote it (`"condition"`) rather than renaming the column — the name is fixed by the consuming tickets.

## Risk classification

`Risk: high` — **confirmed, not inherited.** The ticket carries a DB migration against the live linked project plus a change to the code path that decides which of a user's items the engine is allowed to suggest; `docs/OPERATOR_RULEBOOK.md` §C2 and `.claude/CLAUDE.md`'s lane rule both put "schema/migrations" and irreversible external state on the full lane, and the on-the-fence rule says classify up. The mitigating facts are real and worth recording — the migration is additive-only (no rewrite, no DROP, no type change, no RLS change), and with every existing row defaulting to `false` the engine's output is byte-identical to today until a writer exists — but "small and additive" describes the *blast radius*, not the *reversibility*, and a column added to a shared live project is exactly the one-way door the gate exists for. Designed on Opus, so no model re-invoke is needed.
