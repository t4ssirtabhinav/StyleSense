# SS-034 — Garment Types Registry (EXPAND phase only) — Design

Ticket: [`docs/tickets/raw/SS-034.md`](raw/SS-034.md) · Source proposal: [`docs/proposals/STYLING-ENGINE-V2.md`](../proposals/STYLING-ENGINE-V2.md) §3–§4, Appendix B · Depends on: SS-025 (structural precedent, `007_occasions_registry.sql`)
Architect pass: 2026-08-04 (Sonnet, fast lane)

**This document is the Developer's spec.** It is distilled from the raw ticket and the proposal — do not re-open either for values already fixed here. Every value below is either **[VERIFIED — Appendix B]** (sourced), a direct structural lift from `007_occasions_registry.sql` (cited by line), or **[Architect judgment — needs stylist review]** (my call, flagged so it is never mistaken for sourced fact per CLAUDE.md's "label known vs. guessed").

---

## 1. Scope restatement

Today `wardrobe_category` is a 21-value Postgres ENUM with zero ethnic bottoms, so the styling engine can only ever offer kurta-with-jeans — no scoring change can fix a vocabulary that cannot express the outfit. This ticket does **only** the EXPAND step of the same expand→migrate→contract playbook SS-025 already proved for occasions: create `garment_types` (slug PK, `parent_key` self-referencing hierarchy, closed `slot`/`layer` CHECKs for physics, open `register TEXT[]`/`styling_rules JSONB` for culture), `garment_type_aliases`, and `garment_unknown_types`, then seed the real Indian garment vocabulary — every parent-level rule set, the 10 ethnic bottoms, the drapes, and the `torso_mid` layering types, per Appendix B. **Nothing anywhere in `backend/` or `mobile/` reads these tables yet** — that is an acceptance criterion enforced by a grep-based test, not a claim. `wardrobe_items.category` is untouched; the MIGRATE/CONTRACT phases (Wave 2) are explicitly out of scope.

This design additionally resolves **`BL-109`** — Appendix B.1's highest-value finding that "a kurta set is a SET, not a garment" is unrepresentable in the proposal's §4 DDL sketch — by landing a **type-level** set-composition primitive in this same EXPAND phase (§3.7 below). See §8 for the full reasoning; this is a deliberate, bounded expansion beyond the ticket's literal three-table AC, flagged prominently because this design doc is the only human checkpoint before code exists on the fast lane.

---

## 2. Blast radius

Zero. One new migration file, zero application code changes, zero existing tables altered, zero live user data touched. The only "consumer" of this ticket's output is a test file proving there is no consumer.

---

## 3. Concrete values to use, not invent

### 3.1 `garment_types` — column contract

Structurally lifted from `007_occasions_registry.sql:36-57` (cited lines), swapping `kind` (occasions' closed CHECK) for the proposal §4 DDL's `slot`/`layer` pair (garments' closed CHECK), and dropping `badge_color`/`date_rule`/`tier_gate` (occasion-specific, per the ticket's Technical Notes: *"`badge_color` is occasion-specific and drops out"*).

```sql
CREATE TABLE garment_types (
  key             TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  parent_key      TEXT REFERENCES garment_types(key) ON DELETE RESTRICT
                    CHECK (parent_key IS DISTINCT FROM key),
  label           TEXT NOT NULL,
  labels_i18n     JSONB NOT NULL DEFAULT '{}'::jsonb,

  -- CLOSED structural sets: physics, not fashion. Code MAY switch on these.
  slot            TEXT NOT NULL CHECK (slot IN (
                    'head','torso_base','torso_mid','legs','full_body',
                    'feet','neck','waist','wrist','carry','drape','set')),
  layer           SMALLINT NOT NULL CHECK (layer BETWEEN 0 AND 3),

  -- OPEN vocabulary: data only. Code NEVER switches on these.
  register        TEXT[] NOT NULL CHECK (cardinality(register) > 0),
  base_formality  SMALLINT NOT NULL CHECK (base_formality BETWEEN 0 AND 10),
  coverage        JSONB NOT NULL DEFAULT '{}'::jsonb,
  requires_with   TEXT[],
  pairs_with      TEXT[],
  excludes_with   TEXT[],
  region_scope    TEXT[] CHECK (region_scope  IS NULL OR cardinality(region_scope)  > 0),
  culture_scope   TEXT[] CHECK (culture_scope IS NULL OR cardinality(culture_scope) > 0),
  gender_affinity TEXT[],
  styling_rules   JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  sort_order      INTEGER NOT NULL DEFAULT 100,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_garment_types_active_sort ON garment_types (is_active, sort_order);
CREATE INDEX idx_garment_types_parent      ON garment_types (parent_key);
```

**Deviation from the proposal's §4 DDL sketch, flagged explicitly:** I added `'set'` as a 12th `slot` value (proposal listed 11) and a `CHECK (cardinality(register) > 0)` (proposal declared `register TEXT[] NOT NULL` but didn't forbid `'{}'`, which would otherwise be a silent "no register" hole identical in spirit to the null-vs-empty-array bug `007` exists to prevent for `region_scope`). Both are additive, zero-cost, and reversible since no rows exist yet. `'set'` is what §3.7 (BL-109) needs — see §8.

**Null semantics — copied verbatim from `007_occasions_registry.sql:19-27`, the ticket's own AC #2 requirement:**
- `region_scope IS NULL` means **universal / pan-India**, not "no regions." Same for `culture_scope`.
- The empty array is **forbidden by CHECK** — nobody can write "applies nowhere."
- Canonical applicability predicate (copy verbatim wherever this is ever consumed):
  ```sql
  (region_scope  IS NULL OR :user_region  = ANY(region_scope))
  AND (culture_scope IS NULL OR :user_culture = ANY(culture_scope))
  ```

No GIN index on any `TEXT[]` column — same reasoning as `007`: ~63 rows this ticket, low-hundreds at the eventual 75-95-type ceiling; sequential scan is correct. Revisit only if profiling says otherwise.

**`styling_rules` JSONB shape — Architect judgment, documented in-file as a comment since nothing reads it yet and no upstream spec pins a shape:**
```jsonc
{
  "volume_class": "fitted" | "relaxed" | "voluminous",  // optional; type-level default,
                                                          // superseded by Wave 2's item-level
                                                          // silhouette attribute when present
  "length_yards": 6,                                     // saree children only (B.1 finding #3)
  "note": "free-text authoring rationale, not consumed by code"
}
```
All keys optional; absence means "no opinion," never "false." Wave 2 is free to redefine, extend, or ignore any key here — nothing reads it yet.

### 3.2 `garment_type_aliases` and `garment_unknown_types`

Direct lifts, renaming `occasion_key`→`garment_key`:

```sql
CREATE TABLE garment_type_aliases (
  alias        TEXT PRIMARY KEY CHECK (alias ~ '^[a-z][a-z0-9_]*$'),
  garment_key  TEXT NOT NULL REFERENCES garment_types(key) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_garment_type_aliases_key ON garment_type_aliases (garment_key);

CREATE TABLE garment_unknown_types (
  slug           TEXT PRIMARY KEY,
  occurrences    INTEGER NOT NULL DEFAULT 1,
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_source  TEXT,   -- 'wardrobe_items' | future writers, per 007's precedent
  sample_user_id UUID
);
```

`alias`/`garment_types.key` disjointness is enforced by **resolution order** (canonical key wins before alias lookup), exactly as `007:64-67` — **not** a cross-table constraint, **not** a trigger. Proven by test (§6).

### 3.3 Normalisation + logging functions

Same four-function contract as `007_occasions_registry.sql:174-267`, renamed, **scalar only** (no `garment_normalize_array` — `wardrobe_items.category` is a single value today, not an array like `occasion_tags`; an array wrapper would be unused surface. If Wave 2 ever needs multi-tag garment identity, adding `garment_normalize_array` later is the same cheap, proven pattern):

- `public.garment_normalize_shape(p_raw TEXT) RETURNS TEXT` — not `SECURITY DEFINER` (touches no table).
- `public.garment_normalize_one(p_raw TEXT) RETURNS TEXT` — `SECURITY DEFINER`, `SET search_path = public, pg_temp`. Steps: shape-normalise → canonical key wins → else alias → else keep-and-flag-unknown.
- `public.garment_is_known(p_slug TEXT) RETURNS BOOLEAN` — `SECURITY DEFINER`, same search_path pin.
- `public.garment_log_unknown(p_slug TEXT, p_src TEXT, p_uid UUID) RETURNS void` — `SECURITY DEFINER`, same search_path pin, single atomic `INSERT … ON CONFLICT (slug) DO UPDATE SET occurrences = garment_unknown_types.occurrences + 1, last_seen_at = now()` (no read-then-write — `BL-066`/`BL-036`'s bug class is not introduced here, same posture as `007`).

Contract (identical in spirit to `007`'s, for whenever Wave 2 wires a caller): trim → lower → collapse whitespace/`-` to `_` → strip non-`[a-z0-9_]` → canonical key first → then alias → else keep normalised string and log it. **Never drop. Never fail the write.** Nothing calls these functions in this ticket; they exist inert, exactly as `007`'s did before `008` wired a trigger.

### 3.4 RLS — exact policies

```sql
ALTER TABLE garment_types           ENABLE ROW LEVEL SECURITY;
ALTER TABLE garment_type_aliases    ENABLE ROW LEVEL SECURITY;
ALTER TABLE garment_unknown_types   ENABLE ROW LEVEL SECURITY;
ALTER TABLE garment_set_components  ENABLE ROW LEVEL SECURITY;   -- §3.7

CREATE POLICY "authenticated_read_garment_types" ON garment_types
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_garment_type_aliases" ON garment_type_aliases
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read_garment_set_components" ON garment_set_components
  FOR SELECT USING (auth.role() = 'authenticated');
```

**Deliberately no INSERT/UPDATE/DELETE policy on any of the four tables, and no policy at all on `garment_unknown_types`** — absence of a policy *is* the write-protection mechanism (`007:92-96`'s comment, transferred verbatim). Do not "fix" this with a permissive write policy.

### 3.5 The seed — grouping and defaults

Unless a table below overrides it: `labels_i18n = '{}'` (no approved translations exist — same root cause as `BL-090`, not a new gap), `coverage = '{}'`, `excludes_with = NULL`, `gender_affinity = NULL`, `is_active = true`, `styling_rules = '{}'` except where `length_yards`/`volume_class` is called out. `layer` convention (Architect judgment, documented here since nothing pins it): **0 = base garment** (tops/bottoms/full-body/sets), **2 = worn-over layering** (drapes, jackets/coats). Layers 1 and 3 are reserved, unused this ticket, for a future underlayer/heavy-outerwear granularity — the CHECK already allows them so this needs no migration later.

All `base_formality`/`register`/`coverage`/`styling_rules` values below not directly sourced from Appendix B are **[Architect judgment — needs stylist review before any scoring code consumes them]**, mirroring the proposal's own §10 caveat on the taxonomy. `pairs_with`/`requires_with` marked **[VERIFIED — B.2]** are transcribed verbatim from the proposal's sourced table.

#### Parents (8 top-level rule sets — not the ticket's approximate "~15": see note below)

| key | slot | layer | register | base_formality | requires_with / pairs_with | note |
|---|---|---|---|---|---|---|
| `ethnic_top` | torso_base | 0 | `{ethnic}` | 4 | pairs_with `{ethnic_bottom}` | |
| `ethnic_bottom` | legs | 0 | `{ethnic}` | 4 | pairs_with `{ethnic_top}` | |
| `modern_bottom` | legs | 0 | `{western,athleisure,streetwear}` | 2 | | cargo/joggers/dungarees — deliberately **not** nested under `ethnic_bottom` (wrong register for volume-balance/register-coherence rules) |
| `drape` | drape | 2 | `{ethnic}` | 5 | | |
| `layering_jacket` | torso_mid | 2 | `{ethnic,indo_western}` | 6 | | the fix for "dead outerwear" (Appendix A #11) |
| `saree` | full_body | 0 | `{ethnic}` | 7 | requires_with `{blouse,petticoat}` | `petticoat` is **deliberately not seeded** — see §7 edge case 9 |
| `full_body_garment` | full_body | 0 | `{ethnic,western,indo_western,resort}` | 5 | | generic one-piece parent; sherwani/kaftan/jumpsuit/phiran |
| `garment_set` | set | 0 | `{ethnic}` | 6 | | BL-109 resolution — §3.7 |

**Note on parent count:** the ticket's Technical Notes budget "~15 parent rows." This design uses 8. I chose not to pad to ~15 with placeholder parents that would have zero real children this ticket — every slot actually populated below has exactly one parent demonstrating the hierarchy/override mechanism the AC requires (`parent_key` usage + at least one child overriding a parent value), which is what "~15" was a proxy for, not a literal target. The unused budget is left unused rather than spent on invented rows.

#### Children of `ethnic_top` (8)

| key | register (if ≠ parent) | base_formality (if ≠ 4) | requires_with / pairs_with / scope | note |
|---|---|---|---|---|
| `kurta` | `{ethnic,indo_western}` | | pairs_with `{ethnic_bottom,modern_bottom}` | **No `kurti` row** — length difference, not a sibling type (B.1 finding #2; raw ticket edge case). Length is Wave 2's item-attribute job. |
| `anarkali` | | 7 | | floor-length flared kurta form; distinct silhouette, not just kurta+attribute |
| `angrakha` | | 6 | | |
| `choli` | | 7 | pairs_with `{lehenga_skirt,ghagra_chaniya}` | |
| `blouse` | | 6 | | the saree's **required** companion (B.1 finding #4's flip side) |
| `kameez` | | 4 | pairs_with `{salwar,churidar}` | |
| `crop_top` | `{western,indo_western,streetwear}` | 2 | | |
| `pathani` | | 5 | culture_scope `{muslim}` | Eid scenario, Appendix A #7 |

#### Children of `ethnic_bottom` — the 10 from **B.2, verbatim** [VERIFIED] plus 7 regional/two-piece additions

| key | pairs_with [VERIFIED — B.2] | note |
|---|---|---|
| `palazzo` | `{kurti,kurta,crop_top}` | wide-legged, flowing |
| `churidar` | `{kurti,kurta}` | close-fitting, gathers at ankle — `kurti` in `pairs_with` is B.2's own sourced text; the type itself is not seeded, per the kurta/kurti decision above; leave the string as-sourced since it is descriptive metadata, not an FK |
| `sharara` | `{kurti}` | flared, thigh-fitted; wedding-associated |
| `patiala_salwar` | `{kurti,kurta}` | loose, heavily pleated |
| `gharara` | `{kurti}` | flared, heavy embroidery; wedding/regal |
| `dhoti_pants` | `{kurta}` | indo-western hybrid drape-design |
| `cigarette_pants` | `{kurti,kurta}` | slim tailored, contemporary |
| `culottes` | `{kurta}` | knee-length flared |
| `leggings` | `{kurta,kurti}` | register `{ethnic,indo_western}` — B.1 finding #5's own example of why register must be multi-valued |
| `salwar` | `{kameez,kurta}` | loose pleated, tapered at ankle |

Additions beyond the literal 10, justified by the raw ticket's own named edge cases (not scope creep — each closes a specific, already-flagged gap):

| key | region_scope | requires_with / pairs_with | base_formality override | note |
|---|---|---|---|---|
| `mekhela` | `{assam}` | requires_with `{sador}` | | **half of B.1 finding #4** — mekhela sador is genuinely two-piece; modelling it as one `full_body` type would make its components unmatchable, per the raw ticket's edge case bullet. Deliberately two rows, not one `mekhela_sador` row. |
| `mundu` | `{kerala}` | requires_with `{neriyathu}` | | other half of finding #4 — mundum neriyathum |
| `dhoti` | | pairs_with `{kurta,pathani}` | | traditional wrap, distinct from indo-western `dhoti_pants` |
| `lungi` | | pairs_with `{kurta}` | | region deliberately left `NULL` (universal) — B.4 itself scopes it to "South India, Bengal, Northeast," too broad a set to pin confidently without a controlled region vocabulary (see §8's new backlog row) |
| `veshti` | `{tamil_nadu}` | pairs_with `{kurta}` | | |
| `ghagra_chaniya` | `{rajasthan,gujarat}` | pairs_with `{choli}` | 8 | demonstrates the AC's "children override only where they differ" — festive register, not everyday |
| `lehenga_skirt` | | pairs_with `{choli,blouse}` | 8 | same override pattern |

#### Children of `modern_bottom` (3) — the ticket's own "genuinely-missing modern types," bottom half

`cargo_pants`, `joggers`, `dungarees` — all `register` = parent's, `base_formality` = 1 (joggers/cargo) except `dungarees` = 2.

#### Children of `drape` (7)

`dupatta`, `stole`, `shawl`, `odhni`, `phulkari_dupatta` (region_scope `{punjab}`), `sador` (region_scope `{assam}`, requires_with `{mekhela}`), `neriyathu` (region_scope `{kerala}`, requires_with `{mundu}`). All register `{ethnic}`, base_formality 5 except `phulkari_dupatta` = 7 (festive).

#### Children of `layering_jacket` (5 — exactly the ticket's named list)

`nehru_jacket`, `waistcoat`, `blazer` (register `{ethnic,indo_western,western}`, base_formality 6), `shrug`, `koti`.

#### Children of `saree` (3)

| key | region / culture | styling_rules.length_yards | note |
|---|---|---|---|
| `nauvari` | region `{maharashtra}` | 9 | 9-yard, dhoti-style drape — **cannot** be draped from a 6-yard saree (B.1 finding #3) |
| `madisar` | region `{tamil_nadu}`, culture `{tamil_brahmin}` | 9 | |
| `kanjeevaram` | region `{tamil_nadu}` | 6 (inherits parent default) | primarily a weave/fabric distinction, arguably an item attribute rather than a type — kept as a row because B.4 sources it by name; flagged for Wave 2's attribute-vs-type review, not re-litigated here |

Parent `saree` itself carries `styling_rules.length_yards = 6` (the standard/default drape).

#### Children of `full_body_garment` (4)

| key | register (if ≠ parent) | base_formality | layer override | note |
|---|---|---|---|---|
| `sherwani` | `{ethnic}` | 8 | **2** (not 0) | worn as an outer coat over kurta-pyjama — the second worked example of a per-child override the AC asks for |
| `kaftan` | | 3 | | resort wear |
| `jumpsuit` | `{western,athleisure,streetwear}` | 3 | | |
| `phiran` | `{ethnic}` | 4 | | region_scope `{kashmir}`; winter-specific |

### 3.6 `garment_type_aliases` seed (representative, not exhaustive — same posture as `007`'s 8 for 12 occasions)

| alias | garment_key |
|---|---|
| `plazo` / `palazzos` | `palazzo` |
| `churidaar` / `churidars` | `churidar` |
| `shalwar` / `salwaar` | `salwar` |
| `patiala` / `patiyala` | `patiala_salwar` |
| `ghararah` | `gharara` |
| `shararaa` | `sharara` |
| `dhoti_pant` | `dhoti_pants` |
| `cigarette_pant` / `cigarette_trousers` | `cigarette_pants` |
| `culotte` | `culottes` |
| `legging` | `leggings` |
| `dupattas` / `dupata` | `dupatta` |
| `nehrujacket` / `nehru_coat` | `nehru_jacket` |
| `croptop` / `crop-top` | `crop_top` |
| `kurta_suit` | `kurta_set` |
| `punjabi_suit` | `salwar_kameez_set` |
| `coord_set` / `co-ord` | `co_ord_set` |

### 3.7 `garment_set_components` — the BL-109 resolution

```sql
CREATE TABLE garment_set_components (
  set_key       TEXT NOT NULL REFERENCES garment_types(key) ON DELETE RESTRICT,
  component_key TEXT NOT NULL REFERENCES garment_types(key) ON DELETE RESTRICT,
  role          TEXT NOT NULL CHECK (role IN ('top','bottom','drape','layer','footwear')),
  is_required   BOOLEAN NOT NULL DEFAULT true,
  sort_order    INTEGER NOT NULL DEFAULT 100,
  PRIMARY KEY (set_key, component_key),
  CHECK (set_key IS DISTINCT FROM component_key)
);
CREATE INDEX idx_garment_set_components_set ON garment_set_components (set_key);
```

`component_key` may point at a **parent** row (e.g. `ethnic_bottom`) to mean "any child of this parent satisfies the slot" — deliberate, not a shortcut bug; a future consumer resolves it via `parent_key`, exactly the way `parent_key`-based inheritance already works for `styling_rules`.

**Children of `garment_set` (8)** — B.3's 8 canonical women's forms, with `saree` swapped for `co_ord_set` (reasoning in §8):

| key | base_formality | components (`role`: `component_key`, required?) |
|---|---|---|
| `kurta_set` | 5 | top: `kurta` (req) · bottom: `ethnic_bottom` (req, any child) · drape: `dupatta` (optional) |
| `salwar_kameez_set` | 5 | top: `kameez` (req) · bottom: `salwar` (req) · drape: `dupatta` (req) |
| `anarkali_set` | 7 | top: `anarkali` (req) · bottom: `churidar` (req) · drape: `dupatta` (optional) |
| `sharara_set` | 8 | top: `kurta` (req) · bottom: `sharara` (req) · drape: `dupatta` (req) |
| `gharara_set` | 8 | top: `kurta` (req) · bottom: `gharara` (req) · drape: `dupatta` (req) |
| `lehenga_choli_set` | 9 | top: `choli` (req) · bottom: `lehenga_skirt` (req) · drape: `dupatta` (req) |
| `half_saree_set` | 8 | top: `blouse` (req) · bottom: `lehenga_skirt` (req) · drape: `dupatta` (req, **approximation** — half-saree's upper drape ("oni"/langa-voni) is larger/differently draped than a standard dupatta; flagged for the regional follow-on tail, not fixed here) |
| `co_ord_set` | 3 (register `{western,athleisure,streetwear}`) | top: `crop_top` (req) · bottom: `modern_bottom` (req, any child) |

That is ≈20 `garment_set_components` rows total. `role` values above are illustrative of the CHECK's vocabulary, not a fixed 1:1 to `slot` — deliberately simpler, since this table's job is "what fills this bundle," not "what body part this occupies" (that's still `garment_types.slot`, unchanged).

---

## 4. Files to create/modify

| Path | Action |
|---|---|
| `supabase/migrations/014_garment_types_registry.sql` | **new** — everything in §3. Single EXPAND-only file, no migrate/contract siblings (unlike SS-025's 007/008/009 trio) — this is deliberate; see §9's risk note. |
| `backend/tests/test_db_schema.py` | **modify** — append new test functions (do **not** create a separate schema-test file; every prior ticket's schema tests live in this one file — `test_occasion_registry_tables_exist`, `test_ai_cost_ledger_table_exists_with_generated_cost_paise_column`, `test_suggestion_log_tables_exist`, etc. are the precedent). See §6.1. These tests are gated by the existing module-level `pytestmark = skipif not SUPABASE_DB_URL` — same as every prior addition to this file. |
| `backend/tests/test_garment_registry_purely_additive.py` | **new** — the grep-based "nothing reads it" test, §6.2. **Must not** depend on `SUPABASE_DB_URL` or any live connection — it is a pure filesystem/text-search test and must run in every CI invocation, unlike the schema tests above. |

**No other file in `backend/` or `mobile/` is created or modified.** That absence is itself the AC — verified by the new test above, not merely asserted here.

---

## 5. Applying it

Same established practice as SS-025/SS-029/SS-033 (`docs/worklog/SS-015.md`'s precedent): the **Developer** applies the migration with `supabase db push` against the linked project (`mefpfykuinasgkpfhmzk`) during the Developer phase, then confirms `supabase db diff --linked` is empty.

**`BL-110` is live risk here, not hypothetical** — it already happened once (SS-028/SS-029's `011`/`012` collision, 2026-07-31). Wave 1.5 has four migration-bearing tickets (`013` SS-033, `014` SS-034, `015` SS-035, `016` SS-036) potentially running in parallel worktrees. Serialize the `db push` step across them even though the code work is parallel; if `db diff --linked` is not empty after this ticket's push, **report the exact diff — do not loosen `.github/workflows/supabase-migrations.yml`'s filter** (`BL-060`'s standing directive, already violated-and-fixed once).

No data fixture capture is needed before this push (unlike SS-025's §7.1) — this migration touches zero existing tables and zero existing rows.

---

## 6. Test plan

### 6.1 `backend/tests/test_db_schema.py` (append; needs `SUPABASE_DB_URL`, live-DB tests)

| Test | Asserts |
|---|---|
| `test_garment_registry_tables_exist` | `garment_types`, `garment_type_aliases`, `garment_unknown_types`, `garment_set_components` all exist in `information_schema.tables` |
| `test_garment_types_slot_check_is_closed` | inserting a row with `slot = 'bogus'` raises `CheckViolation`; inserting with `slot = 'set'` succeeds (proves the 12th value actually landed) |
| `test_garment_types_parent_key_self_reference_rejected` | `UPDATE garment_types SET parent_key = key WHERE key = 'kurta'` raises `CheckViolation` |
| `test_garment_types_region_and_culture_scope_reject_empty_array` | inserting `region_scope = '{}'` raises `CheckViolation`; `region_scope = NULL` succeeds |
| `test_garment_types_register_rejects_empty_array` | inserting `register = '{}'` raises `CheckViolation` (the deviation flagged in §3.1) |
| `test_garment_type_aliases_seeded_and_disjoint_from_garment_keys` | alias set from §3.6 ∩ `garment_types.key` set is empty |
| `test_garment_normalize_one_resolves_key_before_alias` | `garment_normalize_one('palazzo')` returns `'palazzo'` even given a hypothetical colliding alias row inserted mid-test — same collision-is-inert proof as `007`'s occasion test, **not** a constraint |
| `test_garment_normalize_one_maps_known_aliases` | `garment_normalize_one('plazo')` → `'palazzo'`; `garment_normalize_one('  Cigarette Pant ')` → `'cigarette_pants'` (shape + alias together) |
| `test_garment_normalize_one_keeps_and_logs_unknown` | `garment_normalize_one('lehenga_skirt_xyz')` returns the normalised-but-unmapped string; a matching row now exists in `garment_unknown_types` with `occurrences = 1` |
| `test_garment_log_unknown_increments_on_repeat` | calling `garment_log_unknown` twice with the same slug yields `occurrences = 2`, not two rows (atomic upsert, no read-then-write) |
| `test_garment_normalisation_functions_are_security_definer_with_pinned_search_path` | mirrors `test_normalisation_functions_are_security_definer_with_a_pinned_search_path` (line 497) for the four garment functions |
| `test_garment_types_seed_covers_the_ten_sourced_ethnic_bottoms` | the 10 B.2 keys (`palazzo`, `churidar`, `sharara`, `patiala_salwar`, `gharara`, `dhoti_pants`, `cigarette_pants`, `culottes`, `leggings`, `salwar`) all exist with `parent_key = 'ethnic_bottom'` |
| `test_no_kurti_row_exists` | `SELECT 1 FROM garment_types WHERE key = 'kurti'` returns no rows — the B.1 finding #2 decision, asserted so a future ticket can't silently reintroduce the sibling-type mistake |
| `test_mekhela_and_mundu_two_piece_garments_are_not_full_body` | `mekhela`/`mundu` have `slot = 'legs'`, not `'full_body'`, and each carries the other in `requires_with` |
| `test_saree_children_carry_the_correct_length_yards` | `nauvari.styling_rules->>'length_yards'` and `madisar`'s both `= '9'`; `saree` (parent) `= '6'` |
| `test_garment_set_components_resolve_to_seeded_types` | every `set_key`/`component_key` in `garment_set_components` exists in `garment_types` (FK already guarantees this; test documents the intent — a type named in `requires_with`/`pairs_with` free-text arrays has **no** such guarantee, which is the next test) |
| `test_unseeded_requires_with_target_is_a_documented_gap_not_a_crash` | `saree.requires_with` contains `'petticoat'`, which has **no** row in `garment_types` — assert this is true (not accidentally fixed) and that no CHECK/FK exists on `requires_with`'s contents, i.e. the schema permits this by design (raw ticket edge case: "must not break; treat as unsatisfiable requirement surfaced as a gap, not an error") |
| `test_rls_enabled_on_all_four_garment_tables` | `pg_class.relrowsecurity` true for all four |
| `test_only_select_policies_exist_on_garment_types_aliases_and_set_components` | exactly one `SELECT`-only policy per table for those three; zero for `garment_unknown_types` |
| `test_authenticated_cannot_write_garment_types_but_service_role_can` | manual/live — see §6.3 |

### 6.2 `backend/tests/test_garment_registry_purely_additive.py` (new — no DB, runs unconditionally)

| Test | Asserts |
|---|---|
| `test_no_backend_source_references_garment_registry_identifiers` | walks `backend/` excluding `backend/tests/` and `backend/scripts/`; none of the literal strings `garment_types`, `garment_type_aliases`, `garment_unknown_types`, `garment_set_components`, `garment_normalize_one`, `garment_normalize_shape`, `garment_is_known`, `garment_log_unknown` appear in any `.py` file |
| `test_no_mobile_source_references_garment_registry_identifiers` | same walk over `mobile/` excluding `mobile/__tests__/`, same identifier list, `.ts`/`.tsx` files |
| `test_identifier_list_matches_the_migration_file` | sanity check the other way: parse `014_garment_types_registry.sql` and assert every `CREATE TABLE`/`CREATE FUNCTION` name found there is in this test's own identifier list — so a future rename of one of these objects fails this test loudly instead of the grep silently checking a stale name forever |

This is the AC's literal requirement ("asserted by a grep-based test, so purely additive is checked rather than claimed") — deliberately scoped narrower than a generic-word search (does **not** search for `"kurta"`, `"saree"`, etc., since those already appear legitimately as existing `wardrobe_category` ENUM values in shipped code and would be false positives).

### 6.3 Manual / live verification (QA)

1. **RLS write-protection**, both directions: `INSERT INTO garment_types (...)` with an `authenticated` JWT fails with a row-level-security error; the same insert with the `service_role` key succeeds. Repeat for `garment_set_components`.
2. **Drift check**: `supabase db diff --linked` is empty after push (§5).
3. **The "nothing reads it" AC end-to-end**: confirm `test_garment_registry_purely_additive.py` actually ran (not skipped) in the CI log for this PR — it is the one test in this ticket that must never be gated behind `SUPABASE_DB_URL`.

No mandatory regression scope against any shipped ticket — nothing shipped reads these tables, so nothing shipped can regress.

---

## 7. Edge cases

Carried forward from the raw ticket, with the concrete row-level resolution noted where this design closes it outright:

1. **Deactivated parent, active child** — `is_active` is never inherited. Not separately tested beyond the existing `is_active`/`sort_order` index; no seeded row currently exercises this (no parent is seeded `is_active = false`), so this is a structural guarantee (no inheritance trigger exists to violate it), not something this seed can positively demonstrate. Flagged, not closed.
2. **`region_scope = NULL` vs `'{}'`** — CHECK makes the second impossible; tested (§6.1).
3. **Alias/key collision** — inert by resolution order; tested (§6.1), not a constraint (matches `007`'s deliberate precedent).
4. **`requires_with` naming an unseeded type** — `saree → petticoat` is the seed's own live example of this, not merely a hypothetical; tested (§6.1).
5. **Two-piece regional garments are not `full_body`** — `mekhela`/`sador` and `mundu`/`neriyathu` are seeded as four separate rows, never as one `*_full_body` type; tested (§6.1).
6. **9-yard vs 6-yard sarees** — `nauvari`/`madisar` carry `styling_rules.length_yards = 9`; `saree` (parent) carries `6`; tested.
7. **Kurta vs kurti** — no `kurti` row exists; tested as a negative assertion so this decision can't silently regress.
8. **(new) The `'set'` slot value and `garment_set_components` table are outside the raw ticket's literal three-table AC** — flagged prominently in §1/§3.1/§8, not silently added.
9. **(new) `petticoat` is deliberately unseeded** — it is the seed's chosen worked example of edge case 4 above, not an oversight. A follow-on `INSERT` closing it is cheap whenever anyone wants to.
10. **(new) No controlled vocabulary exists for `region_scope`/`culture_scope` strings** — unlike `occasions.badge_color` (closed CHECK against 4 tokens), region/culture strings here are free `TEXT[]` with nothing stopping `'tamil_nadu'` and `'tn'` from silently fragmenting the same concept across future `INSERT`s. Logged as a new backlog row (§8), not fixed here — fixing it would mean building a `regions`/`cultures` registry, which is more schema surface than an EXPAND-phase ticket should absorb.
11. **(new) `half_saree_set`'s drape component is an approximation** (§3.7) — flagged in the seed itself, not hidden.
12. **(new) `kanjeevaram` is arguably a fabric attribute wearing a type's clothing** — kept as a row per B.4's sourcing, flagged for Wave 2's attribute-vs-type review rather than resolved unilaterally here (that decision belongs with whoever designs `garment_attribute_specs`).

---

## 8. BL-109 resolution — decided, not just noted

**Decision: land a type-level set-composition primitive in this EXPAND phase** (`garment_set` parent type, `'set'` as a 12th `slot` value, and the new `garment_set_components` junction table, §3.7) — **not** the "declare `requires_with` interim, defer entirely to Wave 2" option the ticket also offered.

**Why, explicitly, since the ticket presented both as valid:**

- The expensive-to-retrofit window BL-109 warns about has two independent halves: (a) retrofitting *after `garment_types` rows exist*, and (b) retrofitting *after real user `wardrobe_items` reference those rows*. This ticket is the **first** time any `garment_types` row is ever created — so half (a) is at its cheapest point *right now*, in this exact migration, and will only get more expensive from the moment this PR merges. Half (b) genuinely hasn't started yet (nothing reads this registry, per the ticket's own AC) and correctly belongs to Wave 2, when `wardrobe_items` actually needs a set-linking mechanism designed against the real assembler code path rather than designed blind today.
- The primitive added is **purely additive and consumed by nothing** — same risk profile as the rest of this ticket. It does not touch `wardrobe_items`, does not change any AI tagging prompt, does not change any engine code, and is fully reversible by `DROP TABLE` with zero blast radius, same as the other three tables.
- `requires_with` (the "interim" option) genuinely cannot express finding #1: it is a directional soft-pairing hint between two standalone types (`saree → blouse`), not "these N types are the decomposition of one purchased/photographed bundle." Declaring it sufficient would have been recording a decision that doesn't actually hold up, which is worse than recording no decision.
- Cost was checked before committing to it: 1 new slot CHECK value, 1 new 5-column junction table, 8 new `garment_types` rows, ~20 junction rows. Small relative to the ~63-row seed this ticket already budgets, and it directly retires the proposal's own "highest-value finding" rather than deferring it a second time (it was already deferred once, from the original §4 DDL sketch to this ticket).

**What is explicitly still NOT decided here, and is Wave 2's job:** how a photographed physical item maps onto this vocabulary — i.e., does a user who photographs one kurta-set SKU get one `wardrobe_items` row typed `kurta_set` (opaque, but now at least machine-decomposable via `garment_set_components`), or three rows individually typed `kurta`/`churidar`/`dupatta` with some new linking column/table connecting them as "bought together"? Both are consistent with what this ticket ships; neither is chosen here, because choosing requires designing against `wardrobe_items` and the tagging/engine consumption path, which this ticket deliberately does not touch.

**Backlog deltas needed in the main checkout's `docs/BACKLOG.md`** (I cannot edit it from this worktree):

- **Move `BL-109` from Active → Resolved.** Resolved by: SS-034 / Architect, 2026-08-04. Note: *"Type-level set-composition landed in the EXPAND migration itself — `garment_set` parent type (new `'set'` slot value) + `garment_set_components` junction table, seeded with 8 canonical bundle forms (7 of B.3's 8, `saree` swapped for `co_ord_set` since a saree's own `requires_with` already covers its bundle case without a redundant row). Item-level consumption (how a photographed `wardrobe_items` row maps onto this — one opaque set-typed row vs. multiple linked rows) is explicitly NOT decided here and is Wave 2's job against the real assembler path; tracked as a new row, see below."*
- **New Active row (`schema` tag)**: *"Garment-set item-level consumption still undesigned — Wave 2 (the taxonomy MIGRATE/CONTRACT phase, or Engine v2, whichever touches `wardrobe_items`/tagging first) must decide how a photographed set SKU is represented at the item level (one row typed as a `garment_set` child, vs. multiple `wardrobe_items` rows linked as 'bought together'), consuming the type-level vocabulary SS-034 already seeded (`garment_types.slot='set'` + `garment_set_components`). Source: SS-034 / Architect, 2026-08-04."*
- **New Active row (`schema` tag)**: *"No controlled vocabulary exists for `garment_types`/`occasions` `region_scope`/`culture_scope` string values — free `TEXT[]` with no CHECK or lookup table means `'tamil_nadu'` and `'tn'` (or similar) could silently fragment the same concept across independent `INSERT`s from different tickets/authors. Occasions' `badge_color` avoided exactly this by using a closed CHECK; region/culture never got the same treatment because the value space is much larger. Needs a `regions`/`cultures` lookup table (small, additive, same EXPAND pattern) before the registry grows past what one author can keep consistent by memory. Source: SS-034 / Architect, 2026-08-04 (raised while seeding `nauvari`/`madisar`/`mekhela`/`mundu`/etc.)."*
- **Re-scan `BL-090`** (no change needed, note only): *"garment_types.labels_i18n ships `'{}'` for the same reason as occasions' — no source of approved translations exists. Same root cause, not a new row."*

---

## 9. Open questions / blockers

**Not blockers for the Developer to start — no human sign-off is required for the ticket to proceed on the fast lane per its `Risk: med` classification (§10) — but flagged because they are judgment calls a reviewer may want to override before or at the PR gate:**

1. **The `'set'` slot value and `garment_set_components` table (§3.7) go beyond the raw ticket's literal three-table AC.** I judged this the correct call given BL-109's explicit "decide, don't just note" instruction (§8), and kept it to the same risk profile as the rest of the ticket (additive, unconsumed, reversible). If the reviewer disagrees with taking on this extra ~25 rows of seed authoring now, the fallback is: drop §3.7 entirely, keep `requires_with` as BL-109's recorded interim position, and re-open `BL-109` (Active, unchanged) rather than Resolved.
2. **`base_formality`/`register`/`coverage`/`styling_rules` values not sourced from Appendix B are my judgment**, same caveat the proposal's own §10 makes about the whole taxonomy. They feed nothing today (`db diff` and the grep test are the only things that touch this data before Wave 2), so getting one wrong costs an `UPDATE`, not a migration — but flagging per CLAUDE.md's verify-vs-guess rule regardless.
3. **`half_saree_set`'s drape component (`dupatta`) is a known approximation** (§3.7) — a dedicated regional drape type would be more accurate; deferred to the follow-on regional tail rather than fixed now.
4. **B.7 modest wear (`abaya`, `hijab`, `burkini`) is deliberately not seeded this ticket** — `pathani` (Eid, men's) is the only modest/culture-scoped addition this round; the raw ticket's cap list doesn't name B.7, and adding it well would need the same care the region/culture backlog row above flags. Left as follow-on regional-tail work, not silently dropped — Appendix A scenario #7 (Muslim family Eid) stays partially unaddressed until then.

---

## 10. Risk classification

**Risk: med — confirmed, not revised.**

Self-attack, since "DB schema/migrations" is one of the rubric's own named high-risk surfaces and the instruction is to classify up when genuinely on the fence: this design does create new tables via a live-project migration, which is schema work in the literal sense. I did not classify it high because the specific thing §C2's one-way-door scrutiny exists to catch — an *irreversible* or *hard-to-undo* change — is not present here in the way it was for SS-025 (which altered live columns, dropped a type and a table, and backfilled real user data in the same PR). This ticket, by contrast:

- creates four **brand-new** tables with **zero existing consumers**, verified by an automated grep test rather than asserted;
- alters **zero** existing tables and touches **zero** existing rows;
- is fully reversible by `DROP TABLE`/`DROP FUNCTION` with no blast radius, because nothing depends on these objects yet;
- deliberately ships **only** the EXPAND step — no MIGRATE, no CONTRACT — unlike SS-025, where those higher-risk steps were bundled into the same ticket/PR.

This is the same reasoning the raw ticket's own Source Note already applied ("purely additive, nothing reads it yet, zero risk to shipped code") and that SS-025's own `007` file demonstrated in isolation before `008`/`009` made that ticket's *overall* classification high. `med` (fast lane) is correct for the work as scoped in this ticket.

**Explicit tripwire for whoever runs Developer/QA:** if anything in this ticket's implementation drifts toward touching `wardrobe_items`, wiring a trigger, or otherwise giving these tables a real consumer before this PR merges, **stop and escalate to a full-lane human gate** — that would be a materially different, higher-risk change than the one this design doc authorizes.
