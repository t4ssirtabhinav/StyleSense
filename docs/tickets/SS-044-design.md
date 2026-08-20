# SS-044 — Indian Garment Types & Category Migration (design)

Tier: `standard` (Est: 20h) · Resolves `BL-132`, `BL-156`

## Scope restatement

`wardrobe_items.category` is a 21-value Postgres ENUM (`wardrobe_category`, `001_initial.sql:7`). SS-034 built the `garment_types` registry (`014`) under registry-native keys (`kurta`, `saree`, `palazzo`, …) that share no values with that enum. `GarmentRegistryAdapter.get_garment_attributes` therefore misses on 100% of live rows, and Engine v2's `volume_balance`/`register_coherence` terms — real, unit-tested code in `engine_v2_attribute_scoring.py` — silently degrade to the neutral 1.0 default on every real wardrobe (`BL-132`). This ticket makes every live category value resolve to a `garment_types` row and makes those two scoring terms produce non-neutral output against real seeded data, verified live rather than by fixture. It also seeds the `feet` slot, which `014` reserved but never populated (`BL-156`).

The ground-check below materially changes the ticket's stated shape on three points: the migration approach (the ticket prefers (b); this design chooses **(a)**, with reasoning), the size of the seeding gap (**far larger than footwear**), and a **third blocker the ticket doesn't mention** without which its own AC #3 cannot pass.

## Ground-check findings (verified against the repo, 2026-08-20)

All paths/claims below were confirmed by reading the actual files, not from the ticket's description.

1. **Next migration number is `022`** — CONFIRMED. `supabase/migrations/` tops out at `021_harden_handle_new_auth_user_email_conflict.sql`.

2. **The adapter is at `backend/services/garment_registry_adapter.py`, not `backend/adapters/`** — the ticket's stated path is wrong. `backend/adapters/garment_registry_repository.py` is the repository (DB access); the adapter (cache + lookup) is in `services/`.

3. **`BL-156` (zero footwear rows) — CONFIRMED, and it substantially understates the gap.** `014`'s seed populates only 6 of the 12 CHECK'd `slot` values: `torso_base`, `legs`, `drape`, `torso_mid`, `full_body`, `set`. There are **zero** rows for `feet`, `head`, `neck`, `waist`, `wrist`, `carry`. So it isn't only the 4 footwear enum values that can never resolve — all 5 `accessory_*` values (`bag`, `jewellery`, `watch`, `belt`, `scarf`) have no target either, and `western_top`, `western_dress`, `indo_western` have no plausible existing row. **~13 of the 21 live enum values need new registry rows**, not 4. This is the bulk of the ticket's real work and is why 20h is credible.

4. **NEW BLOCKER, not in the ticket: `volume_balance` will stay inert even after a perfect category→registry mapping.** `volume_balance_score` (`engine_v2_attribute_scoring.py:130`) skips any pair where either item's `volume_class` is `None`. `volume_class` is read by `_to_garment_attributes` from `garment_types.styling_rules->>'volume_class'`. Grepping `supabase/migrations/` for `volume_class` returns **exactly one hit — a comment in `014` documenting the key's shape**. **Zero seeded rows populate it.** Seeded `styling_rules` values are `'{}'` or `'{"length_yards": N}'`. Therefore AC #3 ("`volume_balance` produces non-neutral scores against a real seeded wardrobe") is **unreachable** unless this ticket also backfills `styling_rules.volume_class`. Logged as `BL-191`; fixed in scope here because it is this ticket's own hard blocker.

5. **The adapter already resolves aliases, with zero code change needed.** `get_garment_attributes` (`garment_registry_adapter.py:107`) normalises `category.strip().lower()`, checks `snapshot.rows` (canonical key) first, then `snapshot.aliases`. `SupabaseGarmentRegistryRepository.fetch_registry` already SELECTs `garment_type_aliases` and returns it in the snapshot. All 21 enum values satisfy `garment_type_aliases.alias`'s `^[a-z][a-z0-9_]*$` CHECK, and none collides with an existing `garment_types.key`. **Approach (a) is a pure data migration requiring no backend code change to the resolution path.**

6. **`CATEGORY_SLOT[item.category]` is a bare subscript on a live scoring path.** `category_completeness_score` (`engine_v2_attribute_scoring.py:91`) indexes `CATEGORY_SLOT` directly, and `styling_rules_defaults.py:79` asserts at import that its keys exactly equal `get_args(WardrobeCategory)`. Widening `category` beyond the 21 Literal values raises `KeyError` at runtime and breaks the import-time assertion.

7. **Blast radius of changing the column's vocabulary: 17 mobile files + the Gemini tagging contract.** `mobile/features/wardrobe/wardrobe.constants.ts`, `wardrobe.types.ts`, generated `mobile/types/supabase.ts`, and 14 test files reference the enum vocabulary; `ai/ports/interfaces.py:202`'s `WardrobeCategory` Literal constrains the vision adapter's output schema (`GeminiVisionAdapter`) and `wardrobe_tagging_service.py`'s write.

8. **The `009` precedent is three migrations, not one.** SS-025 ran `007` (EXPAND: registry + alias table), `008` (columns → TEXT), `009` (CONTRACT: backfill through aliases, then drop the enum). Notably, `009`'s own merge step resolved the split-brain vocabulary **through permanent alias rows** — the same mechanism this design chooses.

## Migration approach: (a) alias rows — chosen. (b) enum→TEXT FK — rejected for this ticket.

The ticket states a preference for (b). **This design chooses (a), and the reasoning is recorded here rather than left implicit**, per the ticket's own instruction.

**Why (b) is wrong *for this ticket*:**

- (b) is not the analogue of `009`; it's the analogue of `008`+`009` **fused**, executed against a column whose vocabulary is coarser than the registry's. The occasion migration could do this because `occasion_type`'s values mapped **1:1 onto same-granularity registry keys** (`wedding` → `wedding_guest`). Garments do not: `footwear_ethnic` is a *formality bucket* spanning jutti/kolhapuri/mojari, and `ethnic_lehenga` maps ambiguously onto `lehenga_skirt` (the garment) vs `lehenga_choli_set` (the bundle). A backfill would have to **invent per-item garment knowledge that the column does not contain** — for every existing row, unverifiably. That is a lossy, irreversible one-way door.
- The vision model cannot emit the finer vocabulary today. `WardrobeCategory`'s 21-value Literal is the Gemini adapter's constrained output schema. Migrating the column without retraining/re-prompting the tagger means new writes keep arriving in the old vocabulary anyway — so (b) buys nothing until a tagging ticket lands, and until then leaves the column in a *mixed* vocabulary, which is strictly worse than a clean two-hop.
- (b) breaks `CATEGORY_SLOT[item.category]` (finding 6) with a runtime `KeyError` on a live weighted scoring term, breaks the import-time assertion, and forces coordinated changes across 17 mobile files, the generated `supabase.ts`, and the tagging contract (finding 7) — none of which advance `BL-132`'s actual goal.
- AC #4 demands reversibility. (a)'s rollback is `DELETE FROM garment_type_aliases WHERE alias IN (...)` plus dropping the new rows — provably lossless, since no existing column value is rewritten. (b)'s rollback must reconstruct 21 enum values from a finer vocabulary, i.e. re-derive discarded information.

**Why (a) is right:** it needs zero application-code change on the resolution path (finding 5), rewrites no user data, is additive-only and therefore trivially reversible, and closes `BL-132` completely — the engine's lookup genuinely resolves, and both scoring terms genuinely activate.

**On the ticket's objection that (a) "leaves a permanent two-hop lookup":** it is not permanent, and it is not a runtime cost. The alias hop happens in an in-memory dict on a TTL-cached snapshot (`garment_registry_adapter.py:114-118`) — one extra dict `.get()`, not a second query. And (a) is precisely the **MIGRATE** phase; a later CONTRACT ticket can still collapse the hop once the tagger emits registry-native keys. Choosing (a) now *preserves* that option; choosing (b) now spends it on guessed data.

**Recorded scope boundary:** this ticket is MIGRATE only. Dropping the `wardrobe_category` enum (CONTRACT) is explicitly **out of scope** and is logged as `BL-192`.

## Files to create/modify

**Create:**

- `supabase/migrations/022_garment_category_resolution.sql` — the whole schema/data change. Three ordered parts, all additive: (1) new `garment_types` rows (bucket rows + fine-grained children, incl. all `feet`-slot rows for `BL-156`); (2) `styling_rules.volume_class` backfill on every row reachable from a live category (finding 4); (3) 21 `garment_type_aliases` rows, one per `wardrobe_category` enum value. Ends with a `-- ROLLBACK:` comment block, matching `014`'s own convention.
- `backend/scripts/ss044_verify_category_resolution.py` — live verification against the linked project, following `ss036_verify_pattern_fabric_registry.py`'s shape exactly (throwaway user, full teardown, prints for an operator, non-zero exit on failure). This script *is* AC #1/#2/#3's evidence; a passing unit test proves nothing new here.
- `backend/tests/test_garment_category_alias_coverage.py` — the fixture-level guards that CI can enforce.

**Modify:**

- `backend/tests/test_garment_registry_purely_additive.py` — SS-034's guard asserts nothing reads the registry tables. That premise is now false by design (SS-038 already reads them; this ticket makes the read *resolve*). Read this file first and update or retire the assertion deliberately, with a comment saying why — do not delete it silently.
- `backend/services/engine_v2.py` — module docstring lines 48-56 assert the LIVE-INERT state as "expected and documented, NOT a bug to work around." That paragraph becomes false when this ticket lands and must be rewritten to describe the resolved state and point at `022`.
- `backend/services/garment_registry_adapter.py` — docstring lines 15-18 claim fallback logging would spam "100% of them today." Update that rationale; the numbers change.

**Explicitly NOT modified** (this is the payoff of approach (a) — confirm each stays untouched):
`ai/ports/interfaces.py` (`WardrobeCategory` Literal), `services/styling_rules_defaults.py` (`CATEGORY_SLOT`/`CATEGORY_FORMALITY`), `services/wardrobe_tagging_service.py`, `mobile/types/supabase.ts` (no column type change ⇒ AC #6 is a no-op, state this explicitly in the worklog), and all 17 mobile files in finding 7.

## Concrete values to use, not invent

### 1. The 21 alias rows (`garment_type_aliases`)

Every live `wardrobe_category` value on the left; the `garment_types.key` it resolves to on the right. Targets marked **NEW** are created by part (1) of this migration; the rest already exist in `014`.

| `wardrobe_category` value | → `garment_key` | Status |
|---|---|---|
| `western_top` | `modern_top` | NEW |
| `western_bottom` | `modern_bottom` | exists (parent) |
| `western_dress` | `dress` | NEW |
| `western_outerwear` | `modern_outerwear` | NEW |
| `ethnic_kurta` | `kurta` | exists |
| `ethnic_saree` | `saree` | exists (parent) |
| `ethnic_lehenga` | `lehenga_choli_set` | exists |
| `ethnic_anarkali` | `anarkali` | exists |
| `ethnic_salwar_kameez` | `salwar_kameez_set` | exists |
| `ethnic_dupatta` | `dupatta` | exists |
| `ethnic_sherwani` | `sherwani` | exists |
| `indo_western` | `indo_western_outfit` | NEW |
| `footwear_formal` | `formal_footwear` | NEW |
| `footwear_casual` | `casual_footwear` | NEW |
| `footwear_ethnic` | `ethnic_footwear` | NEW |
| `footwear_sports` | `sports_footwear` | NEW |
| `accessory_bag` | `bag` | NEW |
| `accessory_jewellery` | `jewellery` | NEW |
| `accessory_watch` | `watch` | NEW |
| `accessory_belt` | `belt` | NEW |
| `accessory_scarf` | `scarf` | NEW |

Two mappings are judgment calls, recorded here rather than left silent:

- **`ethnic_lehenga` → `lehenga_choli_set`, not `lehenga_skirt`.** A user photographing "a lehenga" as one wardrobe item almost always means the worn outfit, not the skirt piece alone. `lehenga_choli_set` has `slot='set'` → `assembly_slot='one_piece'` via `GARMENT_SLOT_TO_ASSEMBLY_SLOT`, which is the correct single-item assembly behaviour. This brushes against `BL-116` (item-level set consumption, undesigned) but does not resolve it — see Open questions.
- **`western_outerwear` → new `modern_outerwear`, not the existing `layering_jacket`.** `layering_jacket`'s `register` is `ARRAY['ethnic','indo_western']`. Aliasing a western jacket onto it would make `register_coherence_score` report *false coherence* with ethnic items (its check is `set(a.register) & set(b.register)`). A separate western-register row is required for the score to mean anything.

### 2. New `garment_types` rows

Column order follows `014`'s inserts. `layer` convention from `014`: 0 = base garment, 2 = worn-over. `coverage`/`labels_i18n` default `'{}'`; `is_active` defaults true.

**Bucket rows aliased directly by the enum (13):**

| key | parent_key | label | slot | layer | register | base_formality | volume_class |
|---|---|---|---|---|---|---|---|
| `modern_top` | NULL | Modern Top | `torso_base` | 0 | `{western,athleisure,streetwear}` | 2 | `fitted` |
| `dress` | `full_body_garment` | Dress | `full_body` | 0 | `{western,resort}` | 5 | `relaxed` |
| `modern_outerwear` | NULL | Modern Outerwear | `torso_mid` | 2 | `{western,streetwear}` | 4 | `relaxed` |
| `indo_western_outfit` | `full_body_garment` | Indo-Western Outfit | `full_body` | 0 | `{indo_western}` | 5 | `relaxed` |
| `formal_footwear` | NULL | Formal Footwear | `feet` | 0 | `{western,indo_western}` | 7 | `fitted` |
| `casual_footwear` | NULL | Casual Footwear | `feet` | 0 | `{western,athleisure,streetwear}` | 3 | `fitted` |
| `ethnic_footwear` | NULL | Ethnic Footwear | `feet` | 0 | `{ethnic,indo_western}` | 6 | `fitted` |
| `sports_footwear` | NULL | Sports Footwear | `feet` | 0 | `{athleisure,streetwear}` | 1 | `fitted` |
| `bag` | NULL | Bag | `carry` | 0 | `{western,ethnic,indo_western,streetwear}` | 4 | `fitted` |
| `jewellery` | NULL | Jewellery | `neck` | 0 | `{ethnic,indo_western,western}` | 5 | `fitted` |
| `watch` | NULL | Watch | `wrist` | 0 | `{western,indo_western,athleisure}` | 4 | `fitted` |
| `belt` | NULL | Belt | `waist` | 0 | `{western,indo_western,streetwear}` | 3 | `fitted` |
| `scarf` | NULL | Scarf | `drape` | 2 | `{western,indo_western}` | 3 | `relaxed` |

The four accessory buckets carry deliberately **broad** `register` arrays: a watch or a bag is register-neutral in practice, and a narrow array would make `register_coherence_score` invent a 0.5 penalty for pairing a watch with a kurta. Breadth here is the conservative choice — it yields "no opinion" (1.0) rather than a fabricated penalty. `scarf` is deliberately western-register (a `dupatta`/`stole` is the ethnic drape and already exists).

**Fine-grained `feet` children (9) — `BL-156`'s real content, not plumbing.** These are seeded for the future (a finer tagger, and `preferred_footwear_categories` work); no alias points at them today. All `slot='feet'`, `layer=0`, `volume_class='fitted'`.

| key | parent_key | label | register | base_formality | region_scope |
|---|---|---|---|---|---|
| `jutti` | `ethnic_footwear` | Jutti | `{ethnic}` | 6 | `{punjab,rajasthan}` |
| `mojari` | `ethnic_footwear` | Mojari | `{ethnic}` | 6 | `{rajasthan}` |
| `kolhapuri` | `ethnic_footwear` | Kolhapuri | `{ethnic,indo_western}` | 5 | `{maharashtra}` |
| `chappal` | `casual_footwear` | Chappal | `{ethnic,western,streetwear}` | 2 | NULL |
| `sandal` | `casual_footwear` | Sandal | `{western,resort,streetwear}` | 3 | NULL |
| `sneaker` | `casual_footwear` | Sneaker | `{western,athleisure,streetwear}` | 2 | NULL |
| `loafer` | `formal_footwear` | Loafer | `{western,indo_western}` | 6 | NULL |
| `oxford` | `formal_footwear` | Oxford | `{western}` | 8 | NULL |
| `heel` | `formal_footwear` | Heel | `{western,indo_western}` | 7 | NULL |

`region_scope` values reuse the exact strings `014` already uses (`punjab`, `rajasthan`, `maharashtra`, …) — still an uncontrolled vocabulary (`BL-117`), consumed here, not fixed here.

**Provenance flag, same posture as `014`'s own seed comment:** every `base_formality`, `register`, and `volume_class` value above is **Architect judgment, not verified stylist input**. Flagged once here rather than per-row; folds into `BL-077`'s unrun AI eval, exactly as `014`'s and `styling_rules_defaults.py`'s values already do. Do not present these as sourced.

### 3. `volume_class` backfill on existing `014` rows (finding 4 — the unblocker for AC #3)

Written as `styling_rules = styling_rules || '{"volume_class":"..."}'::jsonb` so `saree`/`nauvari`/`madisar`/`kanjeevaram`'s existing `length_yards` key survives. `_to_garment_attributes` reads only `styling_rules.get("volume_class")` and ignores everything else, so a merge is safe.

Allowed values are exactly `014`'s documented three: `fitted` | `relaxed` | `voluminous`. `_VOLUMINOUS_CLASSES` in `engine_v2_attribute_scoring.py:68` is `{"voluminous", "oversized"}` — **use `voluminous`, not `oversized`**; `oversized` is accepted by the scorer but is not in `014`'s documented vocabulary.

- `voluminous`: `anarkali`, `sharara`, `gharara`, `ghagra_chaniya`, `lehenga_skirt`, `lehenga_choli_set`, `sharara_set`, `gharara_set`, `anarkali_set`, `half_saree_set`, `palazzo`, `patiala_salwar`, `culottes`, `dhoti_pants`, `kaftan`, `phiran`
- `relaxed`: `kurta`, `kameez`, `angrakha`, `pathani`, `salwar`, `mundu`, `mekhela`, `dhoti`, `lungi`, `veshti`, `sherwani`, `jumpsuit`, `co_ord_set`, `kurta_set`, `salwar_kameez_set`, `cargo_pants`, `joggers`, `dungarees`, `saree`, `nauvari`, `madisar`, `kanjeevaram`, all `drape` children, all `layering_jacket` children
- `fitted`: `churidar`, `cigarette_pants`, `leggings`, `choli`, `blouse`, `crop_top`
- Parent rows (`ethnic_top`, `ethnic_bottom`, `modern_bottom`, `drape`, `layering_jacket`, `full_body_garment`, `garment_set`): `relaxed` — parents are alias targets too (`western_bottom` → `modern_bottom`), so leaving them unset would silently re-inert the term for those categories.

**Coverage rule the Developer must enforce:** after the backfill, *every* row in `garment_types` has a `volume_class`. Asserted by a test, not by eye — a single unset row reachable from a live category silently kills the signal for every pair containing it.

### 4. Values to transcribe, not restyle

- The 21 enum values: verbatim from `supabase/migrations/001_initial.sql:7-14`.
- The 12 `slot` values: verbatim from `014`'s CHECK; `GARMENT_SLOT_TO_ASSEMBLY_SLOT` (`styling_rules_defaults.py:229`) already covers all 12 including `feet` → `footwear`, so the new `feet` rows need **no** Python-side change.
- `alias` and `key` must both match `^[a-z][a-z0-9_]*$`. All 21 enum values already do.

## Edge cases

Carried forward from the ticket, plus new ones from the ground-check.

**From the ticket:**

1. **A live category value with no plausible registry match** — after this design there are none: all 21 have an explicit target (table §1). The guard is a test that iterates `get_args(WardrobeCategory)` and asserts an alias row exists for each, so a *future* enum value added without an alias fails CI rather than silently degrading.
2. **Item tagged before SS-034 existed** — no special-casing by tag date. Resolution is a pure function of the column value; `created_at` is never consulted. Nothing in the migration touches `wardrobe_items` at all.
3. **Alias/key collision** — canonical-key-first order is already implemented in both places (`garment_normalize_one`'s step 2 before step 3, and `garment_registry_adapter.py:114-118`). Verified: none of the 21 enum values equals any existing or new `garment_types.key`, so no collision exists today. Proven by test, not by a DB constraint — `014`'s comment explicitly says not to add a trigger for this.
4. **Rollback after partial rollout** — (a) rewrites no user data, so rollback is a pure `DELETE` of the added alias rows + added type rows, plus restoring `styling_rules` on the backfilled rows. **The `volume_class` backfill is the one non-trivially-reversible part** (it merges into an existing JSONB column). Mitigation: the rollback block reverses it with `styling_rules - 'volume_class'`, which restores the exact prior state because **no `014` row had that key** (finding 4 — verified, not assumed).
5. **Verify both scoring terms independently** — the verification script scores two distinct fixtures, one targeting each term, and asserts each is non-neutral on its own. See test plan T7/T8.

**New, from the ground-check:**

6. **`register_coherence` can produce a *worse* outfit ranking once activated.** Today every pair contributes no signal (1.0). After this ticket, a western-top + ethnic-bottom pair scores 0.5 and is actively down-ranked. That is the intended behaviour, but it is a **live behaviour change for real users**, not a no-op — it shifts `ENGINE_V2_RULE_WEIGHTS`'s 0.08-weighted term from constant to variable. The verification script must print before/after portfolio ordering for at least one real wardrobe so the change is observed, not assumed.
7. **A `garment_types` row whose `slot` is not in `GARMENT_SLOT_TO_ASSEMBLY_SLOT` degrades to `None`** (`_to_garment_attributes` returns `None`, logging `garment_registry_unknown_slot`). All 12 slots are covered today, but the new rows use 5 previously-unused slots (`feet`, `carry`, `neck`, `wrist`, `waist`) — the first time that mapping's less-travelled half executes. Assert each new row's `assembly_slot` explicitly (T3).
8. **Accessories now resolve, which changes `volume_balance`'s pair count.** With accessories previously unresolved, a 4-item outfit contributed few or no scored pairs; now nearly all pairs score. Combined with edge case 6, the *magnitude* of both terms changes, not just their activation.
9. **`test_garment_registry_purely_additive.py` will fail by design.** It is SS-034's guard that nothing reads these tables. Treat its failure as expected output of this ticket and update it deliberately (see Files to modify) — not as a flaky test to silence.
10. **Two writers, one shape** — `garment_normalize_one` (SQL) and `get_garment_attributes` (Python) implement the same resolution contract independently. Adding 21 aliases changes both. Assert they agree on all 21 values (T5), or they will drift.

## Test plan

**`backend/tests/test_garment_category_alias_coverage.py`** (new):

- **T1** — iterating `get_args(WardrobeCategory)`, asserts every one of the 21 values appears as an `alias` in the fixture registry snapshot, and that its `garment_key` names an existing `garment_types` key. Fails if a future enum value is added without an alias.
- **T2** — asserts `set(aliases) & set(garment_types.key) == set()` (alias/key disjointness), extending `014`'s existing invariant to the 21 new rows.
- **T3** — for each of the 21 values, `get_garment_attributes(value)` returns non-`None` and its `assembly_slot` is one of the 6 engine slots; explicitly asserts `footwear_*` → `footwear`, `accessory_bag` → `accessory`, `accessory_watch` → `accessory`. This is AC #2's fixture-level guard (`BL-156`).
- **T4** — every returned `GarmentAttributes` for the 21 values has `volume_class is not None` and in `{fitted, relaxed, voluminous}`. Directly guards finding 4; without this the AC #3 blocker can silently return.
- **T5** — parity: for all 21 values, the Python adapter's resolved key equals what `garment_normalize_one` returns (edge case 10). Fixture-level, comparing against a transcribed expectation table.
- **T6** — canonical-key-first: inserting a fixture alias colliding with a real key resolves to the key, not the alias target (edge case 3).

**`backend/tests/test_engine_v2_attribute_scoring.py`** (extend):

- **T7** — `volume_balance_score` returns **< 1.0** for a two-item candidate of `ethnic_lehenga` + `ethnic_anarkali` (both → `voluminous`, neither streetwear), using categories from the real 21-value enum rather than registry-native keys. Asserts the term is no longer structurally neutral.
- **T8** — `register_coherence_score` returns `0.5` for `western_top` + `ethnic_kurta` (disjoint register, not in each other's `pairs_with`) and `1.0` for `ethnic_kurta` + `ethnic_dupatta` (shared `ethnic`). Independent of T7, per the ticket's own instruction to verify both terms separately.
- **T9** — regression: `category_completeness_score` is unchanged for a wardrobe of real enum values (guards that `CATEGORY_SLOT` was not disturbed — the finding-6 hazard).

**`backend/tests/test_db_schema.py`** (extend):

- **T10** — asserts `garment_types` has ≥1 row with `slot='feet'` (`BL-156`'s structural guard) and that no row has an empty `register`.

**`backend/scripts/ss044_verify_category_resolution.py`** (new — this is the actual AC bar, not the tests above):

- **V1** — against the linked project, `SELECT DISTINCT category FROM wardrobe_items` and assert every distinct live value resolves through the real registry snapshot. **AC #1, against live data.** Prints the full distinct-value list with its resolved key.
- **V2** — assert `get_garment_attributes` is non-`None` for all 4 live footwear categories. **AC #2 / `BL-156`.**
- **V3** — creates a throwaway user + a real seeded wardrobe (one item per slot: top, bottom, footwear, accessory), runs Engine v2 end-to-end, and prints the `RuleScore` for `volume_balance` and `register_coherence`, asserting **each is non-1.0 in at least one scored candidate**. **AC #3.** Also prints the top-5 portfolio ordering before/after (edge case 6).
- **V4** — full teardown of every created row. Must handle `BL-131`'s `delete_user()` cleanup gotcha; follow `ss036`'s teardown, including any `garment_unknown_types` capture rows (no FK to `users`, so they survive user deletion).

**Migration verification** (manual, recorded in the worklog):

- `supabase db push` then `supabase db diff --linked` is empty (AC #5). If non-empty, report the exact diff rather than loosening CI's drift filter (`BL-060`).
- `mobile/types/supabase.ts` regeneration is a **no-op** under approach (a) — no column type changes. State this explicitly rather than skipping AC #6 silently.
- Rollback rehearsal: run the `-- ROLLBACK:` block against a local Supabase instance and confirm `garment_types`/`garment_type_aliases`/`styling_rules` return to their pre-`022` state (AC #4, edge case 4).

## Open questions / blockers

1. **None of this ticket's blockers are external** — no third-party dependency, no unprovisioned service. `supabase db push` against the linked project is the only privileged operation, and it is the repo's established pattern.
2. **`volume_class` was never authored by anyone** (finding 4). This design assigns all ~85 values by Architect judgment. They are plausible but unvalidated, and they now *directly* drive a live 0.08-weighted scoring term. A stylist review would materially improve suggestion quality. Logged as **`BL-193`**; not a blocker (the term is strictly better than the constant 1.0 it replaces).
3. **`BL-116` (item-level set consumption) is touched but not resolved.** `ethnic_lehenga` → `lehenga_choli_set` and `ethnic_salwar_kameez` → `salwar_kameez_set` mean two live enum values now resolve to `slot='set'` rows, which `GARMENT_SLOT_TO_ASSEMBLY_SLOT` maps to `one_piece`. That is the conservative, already-documented choice from SS-038, and it is correct for a single photographed item — but it is the first time a *live* category lands on a set row, which is exactly `BL-116`'s subject. Row stays Active, updated with this note. SS-045 (which would have owned it) is cut from the current plan.
4. **`BL-117` (uncontrolled `region_scope`/`culture_scope` vocabulary) is consumed, not fixed.** The 9 new footwear rows add `punjab`/`rajasthan`/`maharashtra` — reusing `014`'s existing strings, so no new drift is introduced, but the row's underlying gap remains. Stays Active, updated.
5. **`BL-064` (colour/pattern vocabulary) is not in scope** — this ticket touches `category` only; `colour_harmony` is unaffected. Confirmed not relevant, no update needed.
6. **AC #7's "existing readers keep working" is satisfied trivially by approach (a)** — enumerated in finding 7 and the "Explicitly NOT modified" list. Under approach (b) this AC would have been the hardest one in the ticket; under (a) it is a confirmation, not a work item. QA should verify the untouched-file list rather than take it on trust.
7. **The ticket's claim that this is "the highest-leverage ticket in the portfolio-scope plan"** references SS-040/048/052/055, which are reserved IDs with no ticket files yet. Not a blocker; noted so the sequencing claim isn't mistaken for a verified dependency.

## Risk classification

`Risk: high` — **confirmed, matching the raw ticket's assumption.** This is a DB migration against the live linked project that seeds ~22 new registry rows and mutates an existing JSONB column on ~63 rows, and it flips two weighted Engine v2 scoring terms from constant to variable, changing suggestion output for every real user (edge cases 6 and 8). Schema/migration surface is a §C2 one-way door on its own; the live behaviour change on real wardrobes independently justifies the full lane.

