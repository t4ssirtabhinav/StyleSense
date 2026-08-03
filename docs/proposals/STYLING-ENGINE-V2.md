# Styling Engine v2 — Taxonomy, Combination Search & the Tuning Dial

**Status:** proposal, needs sign-off. Authored 2026-07-30.
**Supersedes in spirit:** SS-027's v0 engine (shipped, pure, additive — see "Disposition of SS-027").
**Decides:** Epic 3's remaining trajectory, and whether a new schema epic lands before SS-020 assembly.

---

## 0. Verdict up front

SS-027 is a correct **skeleton** and the wrong **ceiling**. It is deterministic, bounded, offline-safe, and structurally incapable of hallucinating an item — all genuinely valuable, all worth keeping. But as the permanent styling engine it caps the product at "conservative and repetitive," and no downstream LLM ticket can lift that cap, because the LLM only ever sees the candidates this engine chose.

Three things are true simultaneously:

1. **The pruning is not what saves money.** The deterministic search is pure Python — microseconds. The only real cost is LLM tokens. SS-027 capped exploration at ~72 candidates *as if* exploration were expensive. It is not. **Exhaustiveness and cost are decoupled, and SS-027 conflated them.** We can explore 50–100× more of the wardrobe for ₹0 extra and still hand the LLM only 5–8 finished candidates.
2. **The taxonomy is the real constraint, not the scorer.** 21 flat categories with no ethnic bottoms (no churidar, salwar, palazzo, dhoti, pyjama, patiala, mundu) is why the engine suggests kurta-with-jeans. No scoring change fixes a vocabulary that cannot express the outfit.
3. **The migration cost only ever goes up.** Freeing the category enum and starting impression logging are both cheap today (tiny user base, few items) and expensive later. Impressions specifically **cannot be backfilled** — every day without them is permanently lost personalization data.

Recommendation: **Strategy 2 + 3 + 5 in sequence** (see §8), starting with the additive half of the schema work *now*, in parallel with SS-028/SS-029 which are unaffected.

---

## 1. What's actually in the database today

Verified by reading migrations `001`–`010` and `ai/ports/interfaces.py`, not recalled.

| Surface | State | Consequence |
|---|---|---|
| `wardrobe_category` | **Postgres ENUM, 21 values** (`001_initial.sql:7-14`) | Adding a garment type = migration + TS regen + app release. The exact problem SS-025 solved for occasions. |
| `occasions` | **Data-driven registry** (SS-025): `parent_key` hierarchy, `kind` CHECK, `formality`, `region_scope`, `culture_scope`, `styling_rules` JSONB, `date_rule`, `tier_gate`, aliases table, unknown-capture table | The template to copy. Already proven in production. |
| `wardrobe_items.subcategory` | **Exists, free TEXT, no vocabulary, unused by engine** | Half the hierarchy is already there and wasted (`BL-064`). |
| `wardrobe_items.pattern` / `.fabric` | **Exist, free TEXT, unused by engine** | Monsoon/summer fabric logic is impossible today but needs no migration. |
| `wardrobe_items.ai_tags` JSONB | Exists, raw AI cache | A ready-made home for new attributes with zero migration. |
| `wardrobe_items.cost_per_wear` | **Generated column, already live** | Budget/rotation features are cheaper than expected. |
| `users.gender`, `.body_type`, `.skin_tone` | **Columns exist, unused** | Plus-size / skin-tone scoring needs no migration to *store* — only to collect and consume. |
| `users.style_preferences` JSONB | Exists | Arbitrary new preferences without migration. |
| `wardrobe_item_wears` | `item_id`, `user_id`, `worn_on` only | **No occasion, no outfit_id.** "Worn recently for *this* occasion" is impossible today. Additive fix. |
| Impressions / feedback | **Does not exist** | No record of what was suggested or how users reacted. Unbackfillable. |
| `app_config` (SS-026) | Live, typed accessor, TTL cache, no-redeploy updates | The tuning dial's substrate already exists. |

**Net:** roughly 60–70% of what a much better engine needs is already in the schema, unused. The blocking gaps are the category enum, the wear-log's missing occasion, and impression logging.

---

## 2. Diagnosis: four conflations

SS-027's limits all trace to four things being merged that should be separate.

**(a) Search breadth conflated with cost.** Capping 8 items/slot bounds Python work that was never expensive. Real bound needed is on *LLM payload*, not on *candidates considered*.

**(b) Garment identity conflated with garment behaviour.** `CATEGORY_FORMALITY["western_top"] = 3` means a silk formal blouse and a ripped band tee are identical to the heaviest rule in the system (weight 0.30). Behaviour should come from attributes, not from the type's name.

**(c) Structural role conflated with cultural vocabulary.** SS-025 already discovered the right split: `kind` is a closed 9-value CHECK (code may switch on it), `key` is unbounded rows. Garments never got that split — the 21-value enum tries to be both role and vocabulary at once.

**(d) Determinism conflated with statelessness.** SS-027 is stateless, so it cannot know what it showed you yesterday, and therefore *must* repeat itself. The fix is not to abandon determinism — it is to make "recently shown / recently worn for this occasion" part of the **input**. Same input → same output still holds; the input just changes daily, so output rotates naturally.

---

## 3. The central idea: score attributes, not identities

This is the one architectural decision everything else follows from.

A garment is not a label — it is a bundle of attributes. If the engine reasons over attributes, **adding a new garment type requires zero engine changes**, because the engine already knows how to style anything describable in the attribute vocabulary.

Four distinct attribute layers, currently all collapsed or missing:

| Layer | Owns | Examples | Where it lives |
|---|---|---|---|
| **Type** (intrinsic to the kind of garment) | slot, layer, cultural register, base formality, typical coverage, what it requires/pairs with | `palazzo` → slot=legs, layer=base, register=ethnic\|indo_western, formality=5, pairs_with=[kurta, crop_top] | new `garment_types` registry |
| **Item** (varies per physical garment) | colour, pattern, fabric, silhouette/fit, size, condition | this kurta is `silhouette=straight, fabric=cotton` | `wardrobe_items` columns + `attributes` JSONB |
| **Person** | body type, size, fit preference, skin tone, region, culture, age band, modesty preference | prefers A-line, avoids bodycon, deep skin tone | `users` (partly exists) + `profile_attributes` |
| **Context** | occasion, weather, time of day, formality, multi-day event position, recent wear | Delhi, January, outdoor evening reception, day 3 of 4 | request params + `occasions` registry |

**This is why you do not need 200 categories.** "Oversized tee" is not a category — it is `western_top` (or `tee`) with `silhouette=oversized`. "Baggy cargos" is `cargo_pants` + `silhouette=baggy`. You need perhaps **60–90 types** plus a rich attribute vocabulary, and the combinatorial expressiveness comes from the attributes. Silhouette is an *item* property, not a type, because the same type comes fitted or baggy.

And it directly yields real styling rules that generalize:
- **Volume balance:** oversized top + baggy bottom = clashing volumes *unless* register is `streetwear` (where it's the intended look). Fitted top + wide-leg palazzo = balanced. One rule, works across every type ever added.
- **Register coherence:** ethnic-register bottom + ethnic-register top scores high; that is what makes *kurta + churidar* beat *kurta + jeans* without anyone hardcoding either pairing.
- **Coverage coherence:** respects modesty preference and occasion norms without enumerating outfits.

---

## 4. Taxonomy: the `garment_types` registry

Copy SS-025's proven shape exactly. Closed CHECK sets for physics; rows for culture.

```sql
CREATE TABLE garment_types (
  key            TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
  parent_key     TEXT REFERENCES garment_types(key) ON DELETE RESTRICT
                   CHECK (parent_key IS DISTINCT FROM key),
  label          TEXT NOT NULL,
  labels_i18n    JSONB NOT NULL DEFAULT '{}'::jsonb,

  -- CLOSED structural sets: physics, not fashion. Code MAY switch on these.
  slot           TEXT NOT NULL CHECK (slot IN (
                   'head','torso_base','torso_mid','legs','full_body',
                   'feet','neck','waist','wrist','carry','drape')),
  layer          SMALLINT NOT NULL CHECK (layer BETWEEN 0 AND 3),

  -- OPEN vocabulary: data only. Code NEVER switches on these.
  register       TEXT[] NOT NULL,          -- ethnic|western|indo_western|athleisure|streetwear|resort
  base_formality SMALLINT NOT NULL CHECK (base_formality BETWEEN 0 AND 10),
  coverage       JSONB NOT NULL DEFAULT '{}'::jsonb,
  requires_with  TEXT[],                    -- saree → [blouse, petticoat]
  pairs_with     TEXT[],                    -- kurta → [churidar, palazzo, jeans, dhoti]
  excludes_with  TEXT[],
  region_scope   TEXT[] CHECK (region_scope  IS NULL OR cardinality(region_scope)  > 0),
  culture_scope  TEXT[] CHECK (culture_scope IS NULL OR cardinality(culture_scope) > 0),
  gender_affinity TEXT[],                   -- advisory, never a hard filter
  styling_rules  JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active      BOOLEAN NOT NULL DEFAULT true,
  sort_order     INTEGER NOT NULL DEFAULT 100
);
```

Plus `garment_type_aliases` (plazo/palazzos/palazzo → `palazzo`) and `garment_unknown_types` capture — both direct lifts from SS-025, which already proved the alias-resolution-order and unknown-capture patterns work.

`slot` semantics fix the dead-outerwear and dropped-dupatta bugs structurally: `drape` is a real slot (dupatta, stole, shawl), `torso_mid` is a real layer (nehru jacket, blazer, shrug), and the assembler must fill every slot the occasion's rules mark as expected.

**Hierarchy = `parent_key`, not a second column.** `ethnic_bottom` → `churidar`, `salwar`, `patiala`, `palazzo`, `dhoti`, `pyjama`, `sharara`. Rules authored at the parent apply to all children; children override only where they differ. That is how you get to 200 types without 200 rule sets — you author maybe 15 parent rule sets.

### Garment types missing today that real users own

`[trained-knowledge — needs verification by web research or a stylist before authoring; do not ship these as facts]`

- **Ethnic bottoms (none exist at all):** churidar, salwar, patiala, palazzo, dhoti, pyjama, sharara, gharara, lehenga-skirt-as-separate, mundu/veshti
- **Ethnic tops beyond kurta:** blouse (saree blouse is a *required* companion piece), choli, kurti (distinct from kurta), angrakha, pathani, panjabi
- **Regional full-body:** nauvari saree, madisar, set-mundu, mekhela chador, mundum neriyathum, phiran
- **Drapes:** dupatta (exists), stole, shawl, odhni, angavastram
- **Layering:** nehru jacket, waistcoat, blazer, shrug, koti
- **Modern/streetwear:** oversized tee, crop top, co-ord set, athleisure sets, cargos, joggers, kaftan, resort wear
- **Modest wear:** abaya, hijab, burkini, long-sleeve variants

Note `blouse` and `petticoat`: a saree is currently one_piece, so a user's blouses are unstylable and unmatched. `requires_with` fixes this — and enables the genuinely useful "you have this saree but no matching blouse" gap insight.

### Item-level extensibility without migrations

Add `wardrobe_items.attributes JSONB` plus a **`garment_attribute_specs`** registry (mirroring the existing `app_config_specs` pattern) defining each attribute's key, allowed values, UI widget, and whether AI may infer it. Adding "sleeve_length" then = one INSERT, and it appears in tagging, scoring, filters, and the edit UI automatically. No app release.

Same pattern for **`profile_attribute_specs`** → answers the "I want to add onboarding/profile questions without an app release" requirement directly. Dynamic renderer + spec rows.

---

## 5. Engine v2 architecture

Four stages, each independently tunable. Stages 1–3 are pure, offline, and effectively free.

```
  Wardrobe + Person + Context + Memory(recent wears/impressions)
        │
  ①  ELIGIBILITY      hard constraints only — never taste
        │             (occasion norms, modesty, weather floor/ceiling, hard colour bans)
  ②  CANDIDATE SEARCH generate WIDE, not narrow
        │             base pairs scored exhaustively → keep top K
        │             each base × top-N per remaining slot (footwear, drape, layer, accessory)
        │             set-templates injected as first-class candidates
  ③  SCORING          attribute-based, pairwise where it matters
        │             + occasion-aware novelty  + person fit  + weather
  ④  PORTFOLIO SELECT MMR diversity + score floor + explicit exploration slot
        │             → 5–8 genuinely different outfits
  ⑤  NARRATE (LLM)    the ONLY paid stage; rank + explain what ③/④ already validated
```

### What each stage fixes

**① Eligibility vs taste separation.** Today the white-at-weddings rule and the "prefers formal shoes" preference live in the same scoring soup. Splitting them means hard rules stay absolute (safety, culture, modesty) while everything else is tunable preference. This is also how you avoid the cream/ivory over-exclusion currently in SS-027 — "avoid white" is a *dominance* judgment, not a per-item hex test.

**② Wide search.** Concretely, for a 200-item wardrobe (60 tops, 50 bottoms):
- today: 8×8 = 64 pairs considered = **~2% of the 3,000 real pairs**
- v2: score all 3,000 base pairs (trivial in Python), keep top ~200, expand each of the top ~50 with the top 3–5 options *per* remaining slot → ~2,000–5,000 fully-assembled scored candidates
- **~70× more exploration, still <100ms, still ₹0.** Then MMR selects 5.

This is the direct answer to "there could be a better combination sitting in the wardrobe that never gets explored." It also fixes the subtler SS-027 bug where **colour harmony is absent from the per-slot capping formula** — so the one top that perfectly complements your best trousers can be pruned before colour is ever considered. In v2, nothing is pruned before it has been scored on the dimensions that matter.

**③ Real scoring.** Pairwise colour (not star-topology against `items[0]`), volume balance, register coherence, fabric×weather, coverage×modesty, person fit, and **occasion-aware novelty**:

> `novelty(item, occasion) = f(days since this item was worn *for this occasion*, days since worn at all, times shown-but-not-worn)`

This needs `occasion_key` + `outfit_id` on `wardrobe_item_wears` — additive, low risk, high value. It is what makes "you wore this to office Tuesday, but it's fresh for a festival" possible, and it kills cross-session repetition without breaking determinism.

**④ Portfolio, not top-5.** Selecting the 5 highest scores gives 5 near-identical outfits — mathematically, the top of a ranked list is highly correlated. Maximal Marginal Relevance instead maximizes `λ·score − (1−λ)·max_similarity_to_already_selected`, with a hard score floor so diversity never surfaces something bad. **λ becomes the "adventurousness" dial.** Plus one reserved *exploration* slot — a valid but non-obvious pairing, labelled as such in the UI ("Try something new"), whose acceptance rate is the single most valuable signal we can collect.

This is also where **partial suggestions** become first-class rather than a failure mode: "this outfit works but you have no ethnic footwear" is a *product surface* (gap insight, shopping hook, style-score driver), not an apology.

**⑤ LLM last.** The LLM never searches. It ranks, narrates, and adds cultural/trend nuance over 5–8 pre-validated candidates. That keeps hallucination structurally impossible (SS-027's real win, preserved) while letting model quality — and cost — vary independently of search quality.

---

## 6. The tuning dial (what you actually asked for)

One `app_config` key set controlling every stage. Same code path; different knobs. Because stages ①–④ are free, **turning the dial up mostly costs nothing** — only stage ⑤ moves the bill.

| Tier | Search pool | Colour | Diversity | LLM | ₹/req `[ESTIMATE]` | Use |
|---|---|---|---|---|---|---|
| **E0** degraded | 500 | star | λ=0.9 | none — rules narrate | **₹0** | both providers down; offline; free-tier over budget |
| **E1** economy | 1,500 | pairwise | λ=0.85 | cheap model, 5 cands | ~₹0.03 | free tier steady state |
| **E2** standard | 5,000 | pairwise + volume | λ=0.75 + 1 explore | mid model, 6 cands | ~₹0.125 | **launch default** |
| **E3** premium | 20,000 | full attribute + templates | λ=0.65 + 2 explore | strong model, 8 cands + per-slot alternates | ~₹0.8 | paid tier, high-stakes occasions |
| **E4** atelier | exhaustive + gap analysis | full | tuned per user | multi-turn, wardrobe critique | ₹2–5 | top tier / concierge |

Every number is a config row (SS-026), so tuning needs no deploy — and `occasions.tier_gate` already exists as the precedent for gating by tier. Cross-cutting knobs worth exposing per-vertical, as you asked: `λ` (adventurousness), novelty half-life, register-strictness, modesty-strictness, volume-balance weight, weather sensitivity, exploration slots.

**The honest catch:** a dial you cannot measure is a dial you turn blind. Tuning is only meaningful with an outcome metric — which requires impression + outcome logging (§7). Without it, "tuned up" is an assertion. **This is the strongest argument for building logging before, not after, the fancy engine.**

---

## 7. Impressions & feedback — the unbackfillable piece

Nothing today records what was suggested. Minimum viable:

- `suggestion_sessions` — request context (occasion, weather, tier, effort tier, engine version, config snapshot hash)
- `suggestion_impressions` — one row per candidate shown: item set, score, rule breakdown, rank, was-exploration flag
- `suggestion_outcomes` — saved / worn / dismissed / shuffled-away / shared

Why this is urgent rather than nice-to-have:
1. **It cannot be backfilled.** Every day shipped without it is permanently lost training data.
2. It is the only way to know whether taste changes helped — i.e. the only way the dial in §6 means anything.
3. It converts the exploration slot from a gamble into a learning mechanism.
4. It is the substrate for genuine personalization later (per-user weights, then bandits) — the actual "app knows me" moat.
5. It powers anti-repetition immediately, even with zero ML.

Cheap now (additive tables, no user-facing change), and it makes every later strategy possible. If only one thing from this document ships early, it should be this.

---

## 8. Strategies

Five coherent postures. They are not mutually exclusive; the recommendation is a sequence.

### Strategy 1 — Patch SS-027 in place
Fix the concrete bugs: assemble outerwear, attach dupatta, vary footwear/accessory per candidate, put colour into the capping key, widen the pool.

- **Difficulty:** low (1 ticket, ~1 day, pure Python, no schema)
- **Risk:** very low — additive, reversible, fully unit-testable
- **Cost:** negligible
- **Pros:** removes the embarrassing failures now; unblocks SS-020 immediately; buys time for the real work
- **Cons:** does nothing for taxonomy, tunability, personalization, or repetition-across-sessions. Still one hardcoded formula over 21 western-shaped categories.
- **Verdict:** **do it, but never mistake it for the answer.** It is triage.

### Strategy 2 — Engine v2: wide search + portfolio diversity + effort dial
Rewrite stages ①–④ as designed in §5–6, still pure/offline, still deterministic, no schema dependency.

- **Difficulty:** medium (2–3 tickets; MMR and pairwise scoring are well-understood, not research)
- **Risk:** low-medium — pure functions, property-testable; main risk is taste regression, which is unmeasurable until §7 exists
- **Cost:** engineering only; runtime cost ≈ ₹0
- **Pros:** directly solves repetitiveness and unexplored combinations; gives the tunable dial; keeps hallucination-proofing and offline degradation; **works on today's 21 categories** so it is not blocked on the migration
- **Cons:** better search over a poor vocabulary still can't suggest kurta+churidar. Diversity without feedback is diversity-by-assumption.
- **Verdict:** **the core of the recommendation.** Highest value per unit risk after triage.

### Strategy 3 — Data-driven garment taxonomy
`garment_types` registry + attribute specs + enum→text migration, following SS-025's 3-step expand/migrate/contract playbook.

- **Difficulty:** high (3–4 tickets; one is `Risk: high` schema work on the core table)
- **Risk:** **highest in this document.** Enum→text on `wardrobe_items.category`; every shipped surface touched (tagging prompt, filters, pickers, grid, edit sheet, generated TS types); loses compile-time exhaustiveness in exchange for extensibility (a trade SS-025 already accepted); needs a re-tagging pass for existing items; AI tagging accuracy degrades as label count grows (mitigation: two-stage coarse→fine prediction constrained to a parent's children, plus alias resolution and unknown-capture, plus user correction as a data asset)
- **Cost:** highest engineering cost; re-tagging is financially trivial *today* (few users, ₹0.024–0.125/item) and grows linearly with adoption
- **Pros:** the only path to real Indian coverage; unlocks region/culture/gender scoping, i18n, tier-gated occasions; **turns "add a category" from an app release into an INSERT**; makes every future engine improvement compound
- **Cons:** slowest to user-visible value; highest blast radius; would delay SS-020 if serialized ahead of it
- **Verdict:** **mandatory, and the additive half should start now.** The expand phase is safe and cheap; the contract phase can wait. Deferring the whole thing is the one decision that gets strictly more expensive with every user we add.

### Strategy 4 — LLM-heavy generative styling
Give a strong model much more of the wardrobe and let it compose outfits directly.

- **Difficulty:** low to build, high to control
- **Risk:** high — reintroduces hallucinated items (the exact failure SS-027 was built to make impossible), non-deterministic, unauditable ("why this outfit?" becomes unanswerable), breaks offline degradation
- **Cost:** 8–79× per call (the ₹1.89 vs ₹0.024–0.125 gap already measured in `EXECUTION-PLAN.md`); scales badly with wardrobe size — a 200-item wardrobe costs ~4× a 50-item one
- **Pros:** genuinely better at cultural nuance, trend awareness, and natural language; no taxonomy authoring needed; would handle regional garments it has seen in training even when our registry lacks them
- **Cons:** unbounded cost, unverifiable output, no moat (anyone can prompt a frontier model), and it cannot answer "does the user own this?" without exactly the structured wardrobe data we'd be bypassing
- **Verdict:** **not as the engine — but yes as a stage-⑤ upgrade and, importantly, as an offline authoring tool.** Use a strong model *once, offline,* to propose `garment_types` rows, `pairs_with` edges, and regional rules for human approval. That converts Strategy 3's authoring burden from months of stylist time into a review queue. High leverage, zero runtime risk.

### Strategy 5 — Learned personalization
Per-user weight learning, then contextual bandits over the rule weights and λ.

- **Difficulty:** medium-high, but **only the logging is needed now**
- **Risk:** low if sequenced correctly (log now, learn later); high if attempted before data exists — cold-start bandits on a handful of users produce noise and erratic suggestions
- **Cost:** logging is nearly free; learning infrastructure is a later, larger investment
- **Pros:** **this is the actual moat.** "The app knows my taste" is not achievable by any fixed formula, and it is the thing a competitor cannot copy by reading our rules. Also the only real answer to "one Python file can't judge everyone's taste."
- **Cons:** needs traffic; needs the exploration slot to avoid a feedback loop that only ever confirms what it already showed; per-user models raise real privacy/explainability questions
- **Verdict:** **ship the logging in the next wave; defer the learning until there is traffic.** Non-negotiable ordering.

---

## 9. Recommended sequence

Guiding principle: **do the irreversible and unbackfillable things first; do the tunable things continuously.**

**Wave 1.5 — now, parallel to SS-028/SS-029** (neither is affected by any of this)
1. **Triage patch** (Strategy 1) on SS-027 — outerwear, dupatta, footwear/accessory variety, colour in the capping key. Small, safe, immediate.
2. **Impressions + outcomes logging** (§7) — additive tables, no user-facing change. *Unbackfillable; every day of delay is lost data.*
3. **`wardrobe_item_wears.occasion_key` + `outfit_id`** — additive; unlocks occasion-aware novelty.
4. **`garment_types` registry — EXPAND phase only** (Strategy 3 step 1): create tables, seed the real Indian vocabulary, author parent-level rules. Purely additive, nothing reads it yet, zero risk to shipped code. Uses Strategy 4's LLM-assisted authoring with human review.

**Wave 2 — the engine**
5. **Engine v2** (Strategy 2): wide search, attribute scoring, MMR portfolio, effort dial as `app_config`. Reads the new registry through an adapter, with a fallback to the 21-value enum so it can ship before the contract phase.
6. **Taxonomy MIGRATE + CONTRACT** (Strategy 3 steps 2–3): `category` → TEXT, backfill, two-stage AI tagging, hierarchical UI picker, drop the enum.
7. **`garment_attribute_specs` + `profile_attribute_specs`** — dynamic attribute and onboarding-question registries. Delivers "add profile questions without an app release."

**Wave 3 — the moat**
8. Progressive profiling (collect fit preference, size, skin tone, modesty, region/culture *in-app over time*, driven by the spec registry rather than a fixed onboarding flow).
9. Fit/size/silhouette and skin-tone scoring — enabled by 7 + 8, gated behind config so it can ship dark and be switched on per cohort.
10. Personalization (Strategy 5 learning), once traffic justifies it.

**Impact on the existing plan**
- **SS-028 / SS-029: unaffected.** Provider routing and cost ledger are orthogonal. Proceed as designed once their blockers are answered — and SS-028's config-driven model routing is exactly what lets stage ⑤ move between E1 and E4 without a rewrite. Its design already supports this.
- **SS-020 (assembly): should consume Engine v2, not SS-027 v0.** If SS-020 ships first, it inherits the single-shoe/no-dupatta output and will need rework. Recommend SS-020 waits for item 5, or is explicitly scoped as a thin seam.
- **SS-021 (style score):** occasion coverage should count against the registry — already flagged; now also gains garment-gap coverage.
- **SS-023 (suggestion UI):** must be designed for portfolio + partial suggestions + the exploration slot from the start. Retrofitting "Try something new" into a finished UI is expensive.
- **SS-024 (footwear module):** largely dissolves — footwear stops being a special module and becomes a slot in the registry.
- **Wave 3 proposals (SS-030 calendar, SS-031 multi-day series):** SS-031 gets much easier with impression logging (no-repeat-across-days is exactly a memory constraint).

---

## 10. Risks, pitfalls, and honest limits

**Self-attack on this proposal:**

- **Attribute values are as unvalidated as SS-027's weights.** Mitigation: attributes are *observable* ("is this oversized?" has an answer) where weights are taste ("how much does colour matter?" does not). Verifiability is the reason to prefer them — not correctness by assumption.
- **Diversity can surface bad outfits.** Mitigation: hard score floor; diversity only reorders *above* the floor.
- **Exploration can embarrass us.** Mitigation: exploration draws only from eligible, above-floor candidates; label it in the UI; cap at 1–2 of 5.
- **200+ types will degrade AI tagging.** This is the most likely technical failure of Strategy 3. Mitigation: two-stage coarse→fine prediction, confidence thresholds, alias resolution, unknown-capture, and treating user corrections as a first-class data asset rather than an error path.
- **Authoring burden is real and recurring.** Mitigation: parent-level rules (≈15 rule sets, not 200), LLM-proposed rows behind human review, and `styling_rules` overrides only for exceptions.
- **Enum→text loses compile-time safety** on the core wardrobe column. This is a genuine trade, already accepted once by SS-025 for occasions. Mitigation: runtime validation + registry-backed types + the alias/unknown backstops.
- **Tuning without measurement is theatre.** Mitigation: §7 before §6 is used in anger.
- **Scope risk:** this is comfortably a multi-epic body of work. Sequenced wrong, it stalls the value loop for weeks. Hence Wave 1.5's bias toward small additive items that unblock nothing and lose nothing.

**Not verified, and should be before authoring:**
- The garment list in §4 is `[trained-knowledge]`, not researched. Real regional coverage (Northeast, Kerala, Bengal, Maharashtra, Tamil Nadu, Punjab, Gujarat, Rajasthan; Muslim/Christian/Sikh/Jain dress norms) needs web research or a stylist.
- Colour-harmony and formality numbers remain unvalidated heuristics (`BL-077`).
- Cream/ivory at Indian weddings — the current hard white filter likely over-excludes appropriate gold-cream banarasi. Needs a cultural call, not a code call.

---

## 11. Decisions needed from you

1. **Does the additive Wave 1.5 start now, in parallel with SS-028/029?** (My recommendation: yes — items 2 and 3 are unbackfillable, item 4 is zero-risk.)
2. **Does SS-020 wait for Engine v2,** or ship thin against SS-027 v0 and accept rework?
3. **Do we commit to the enum→text taxonomy migration** as a Wave 2 `Risk: high` epic? (My recommendation: yes, and the cost only rises with delay.)
4. **Should I run real web research** on Indian regional garment taxonomy before authoring the registry seed? (Recommended — the current list is trained-knowledge and this is a one-way authoring door.)
5. **Cream/ivory at `wedding_guest`** — keep the aggressive filter, or narrow it to true white dominance?
6. **How much are we willing to spend at E3/E4** for paying tiers — this sets the ceiling on stage-⑤ ambition and feeds SS-029's budget rows.

---

## Appendix A — Scenario coverage matrix

Each row is a real user moment. "Today" = SS-027 as shipped. This is the test suite the architecture has to pass, and the source of the §4 vocabulary gaps.

### Region & ethnicity

| # | Scenario | Today | Needed |
|---|---|---|---|
| 1 | Tamil Brahmin wedding — **madisar** saree, 9-yard drape | Type doesn't exist; would tag as `ethnic_saree` and lose the distinction | `madisar` as child of `saree`, `culture_scope`, drape-style attribute |
| 2 | Punjabi sangeet — **sharara / gharara**, heavy dupatta | Neither type exists; dupatta never attached | Ethnic-bottom hierarchy + `drape` slot |
| 3 | Marathi Ganesh Chaturthi — **nauvari** saree, kurta-pyjama | No nauvari, no pyjama | Regional types + `region_scope` |
| 4 | Bengali Durga Puja — **dhoti-panjabi**, garad saree | No dhoti, no panjabi | Ethnic bottoms + regional tops |
| 5 | Kerala Onam — **mundu / set-mundu**, kasavu | No mundu | Regional types; `gender_affinity` advisory |
| 6 | Assamese Bihu — **mekhela chador** (two-piece full-body) | No type; two-piece ethnic sets unrepresentable | `requires_with` set semantics |
| 7 | Muslim family Eid — **pathani**, modest wear, abaya | No pathani/abaya | Types + `culture_scope` + modesty attributes |
| 8 | Christian wedding — white is *appropriate* for the bride | Hard white ban is keyed to `wedding_guest` only, so bride-side nuance is invisible | Culture-scoped colour rules, not one global ban |
| 9 | Gujarati garba — **chaniya choli**, mirror work | Lehenga-ish only; no choli as separate piece | Hierarchy + `requires_with` |

### Occasion & weather

| # | Scenario | Today | Needed |
|---|---|---|---|
| 10 | Mumbai monsoon commute | `fabric` column exists but **unused**; no weather input | Fabric×weather rules; SS-022 weather wired into scoring |
| 11 | Delhi January outdoor evening reception | **Outerwear never assembled** — no shawl, no nehru jacket | `torso_mid` slot filled; layering rules |
| 12 | Chennai May, 38°C | Velvet/silk score identically to cotton | Fabric weight attribute + weather ceiling |
| 13 | Interview vs client meeting vs WFH call | All are formality-6 `professional`; 21 categories can't separate a silk blouse from a band tee | Item-level formality via attributes, sub-occasions in registry |
| 14 | Wedding **series**: mehendi → haldi → sangeet → reception | Stateless engine can repeat the same outfit across all four days | Impression memory + no-repeat-across-series (SS-031) |
| 15 | Gym → office same day | No transition concept | Multi-context requests; `athleisure` register |
| 16 | Goa vacation / resort wear | No kaftan, no resort register | Types + register; travel occasion already exists |
| 17 | Traveling to a different climate than home city | Weather keyed to profile city only | Destination as a context param |

### Body, size, fit, age, skin tone

| # | Scenario | Today | Needed |
|---|---|---|---|
| 18 | **Plus-size** woman preferring A-line/empire, avoiding bodycon | `users.body_type` exists, **unused**; no silhouette vocabulary | Silhouette attributes + fit preferences + person-fit scoring |
| 19 | **Gen-Z streetwear** — oversized tee + baggy cargos + chunky sneakers | "Oversized"/"baggy" are not expressible at all; no cargos/joggers | Silhouette as an **item attribute** (not new categories) + volume-balance rule + `streetwear` register |
| 20 | Petite / tall proportions | Nothing | Proportion attributes; advisory scoring |
| 21 | 55-year-old preferring modest coverage, cotton sarees | No age band, no modesty prefs | `profile_attribute_specs` + coverage rules |
| 22 | **Deep skin tone**, wants jewel tones over pastels | `users.skin_tone` exists, **unused** | Skin-tone-aware colour scoring, config-gated, opt-in |
| 23 | Maternity — temporarily changed fit needs | Nothing; would need a permanent profile edit | Time-bounded profile attributes |
| 24 | Modest dressing — sleeve length, neckline limits | Nothing | Coverage attributes as eligibility rules (§5 stage ①) |

### Wardrobe shape & economics

| # | Scenario | Today | Needed |
|---|---|---|---|
| 25 | New user, 4 items | Honest `limited_options` — but useless | Partial suggestions as a product surface + gap-driven shopping hooks |
| 26 | College student, 15 items, wants maximum outfits | Works, but same shoe every time | Wide search + MMR; `cost_per_wear` already live |
| 27 | Power user, 500 items, forgotten purchases | ~2% of pair space explored; UUID-ordered ties mean the same 8 items surface forever | Wide search + occasion-aware novelty + rediscovery surface |
| 28 | "I wore this kurta to office Tuesday" — festival on Saturday | Wear log has **no occasion**, so recency is global and blunt | `wardrobe_item_wears.occasion_key` |
| 29 | User owns 6 sarees, zero matching blouses | Saree is `one_piece`; blouses unmatchable | `requires_with` → genuine gap insight |
| 30 | Both AI providers down mid-festival-season | **Works today** — full rules-based suggestions, zero network | Preserve as E0. This is a real moat; do not regress it. |

---

## Appendix B — Researched taxonomy seed

`[VERIFIED 2026-07-30 — web research, sources listed at end]`. This replaces §4's trained-knowledge list. Still needs a stylist/native-speaker review pass before it becomes DB rows, but the garment *names* and their pairings are now sourced rather than recalled.

### B.1 Five modeling problems the research exposed

These change the schema slightly, and all five would have been expensive to discover after migration.

1. **"Kurta set" / "suit set" is a SET, not a garment.** Retailers sell kurta + bottom + dupatta as one SKU. A user will photograph either the set or the individual pieces, and we cannot control which. **Requires an explicit `is_set` / set-membership concept** — an item that *is* three garments, or three items that form a known set. Neither the current schema nor §4's design handles this. This is the highest-value finding.
2. **Kurta vs kurti is a length difference, not a different garment** (kurti ≈ hip-length, kurta longer). Argues for one parent type plus a `length` item attribute, not two sibling types — otherwise the AI must make a judgment call that users will disagree with.
3. **9-yard vs 6-yard sarees are physically different garments.** Nauvari (Maharashtra) and madisar (Tamil Brahmin) need 9 yards; a 6-yard saree *cannot* be draped that way. So drape style is partly constrained by the garment, not purely a styling choice — `length_yards` is a real attribute with real consequences.
4. **Several regional "sarees" are genuinely two-piece.** Mekhela sador (Assam) = mekhela (bottom) + sador (drape); mundum neriyathum (Kerala) = mundu + neriyath. These are **not** `full_body` — modeling them as one_piece (as today's schema would) makes their pieces unmatchable. `requires_with` is load-bearing, not a nice-to-have.
5. **Register must be multi-valued.** Leggings and jeans are legitimate modern ethnic bottoms (worn with kurtas daily); dhoti pants, culottes and cigarette pants are indo-western hybrids. Confirms `register TEXT[]` rather than a single value — a single-value register would force wrong choices.

### B.2 Ethnic bottoms — the total gap today (10 sourced types)

Currently **zero** of these exist; this is why the engine can only offer kurta + jeans.

| Type | Description | Pairs with |
|---|---|---|
| `palazzo` | Wide-legged, flowing | kurti, kurta, crop top |
| `churidar` | Close-fitting, gathers at ankle | short kurti, long kurta |
| `sharara` | Flared, embellished, fitted to thigh | short kurti (wedding) |
| `patiala_salwar` | Loose, heavily pleated | short kurti, long kurta |
| `gharara` | Flared, heavy embroidery | short kurti (wedding/regal) |
| `dhoti_pants` | Draped-design, indo-western | short or long kurta |
| `cigarette_pants` | Slim tailored, contemporary | kurti, kurta |
| `culottes` | Knee-length flared | short or long kurta |
| `leggings` | Close-fitting stretch | kurta, kurti, under saree |
| `salwar` | Loose pleated, tapered at ankle | kameez, kurta |

### B.3 Ethnic tops, sets and full-body

- **Tops:** `kurta`, `kurti` (length variant), `anarkali`, `angrakha`, `choli`/`blouse` (a *required* companion, not optional), `kameez`, `crop_top`
- **Sets (8 canonical women's forms):** saree, lehenga choli, salwar kameez, anarkali set, kurta set, sharara set, gharara set, half-saree
- **Skirts:** `ghagra`/`chaniya` (Rajasthan/Gujarat), `lehenga_skirt`
- **Drapes (`drape` slot):** `dupatta`, `odhni`, `stole`, `shawl`, `phulkari_dupatta` (Punjab)

### B.4 Regional variants with `region_scope` / `culture_scope`

| Garment | Region | Note |
|---|---|---|
| `nauvari` / `kasta` saree | Maharashtra | 9-yard, dhoti-style drape, back-tucked pleats |
| `madisar` | Tamil Brahmin | 9-yard |
| `mekhela_sador` | Assam | **two-piece**; muga/pat silk |
| `mundum_neriyathum` / `kasavu` | Kerala | **two-piece**; off-white + gold zari border |
| `phiran` | Kashmir | Loose, warm, embroidered — winter-specific |
| `ghagra_choli` | Rajasthan | choli + ankle-length ghagra |
| `kanjeevaram` | Tamil Nadu | silk saree variant |
| `lungi` | South India, Bengal, Northeast | tube, ~2 yards |
| `veshti` | Tamil Nadu | simple waist drape |
| `dhotar` (kachhi style) | Maharashtra / Bengal | passes between legs |

### B.5 Men's ethnic (currently only `ethnic_kurta`, `ethnic_sherwani`)

`kurta_pyjama`, `sherwani`, `pathani_suit` (Eid-associated), `bandhgala`, `jodhpuri`, `nehru_jacket` (`torso_mid` layer — the fix for dead outerwear), `waistcoat`/`koti`, `dhoti`, `lungi`, `veshti`, `indo_western`

### B.6 Silhouette & fit — **item attributes, never types**

This is the answer to oversized/baggy without category explosion:

- **Silhouette:** `oversized` (boxy, voluminous, deliberately loose), `relaxed` (looser than standard, not shapeless), `regular`, `slim`, `baggy` (80s/90s-inspired), `bodycon` (hugs bust-to-hem in stretch), `a_line` (fits bust/waist, flares to hem — "suits most shapes because it skims the hips"), `empire` (waist seam under bust, floats over midriff), `fit_and_flare`, `sheath`, `straight`, `wide_leg`, `flared`, `tapered`
- **Length:** `crop`, `hip`, `knee`, `midi`, `ankle`, `floor`
- **Coverage:** sleeve length, neckline, midriff — drives modesty rules
- **Modern types needing rows:** `oversized_tee` is `tee` + silhouette; but `cargo_pants`, `joggers`, `co_ord_set`, `kaftan`, `jumpsuit`, `dungarees` are genuinely missing *types*

Two sourced styling rules that generalize across every future type:
- A-line/empire "skim rather than cling" → directly serves plus-size and midriff-conscious preferences
- Volume balance: oversized top + baggy bottom reads as clashing volume unless register is `streetwear`, where it is the intended look

### B.7 Modest wear

`abaya`, `hijab`, `long_sleeve` variants, `burkini` — plus coverage attributes as **eligibility** rules (stage ①), not preferences, since modesty is not a taste dial.

### B.8 Scale estimate

Roughly **75–95 types** across ~11 slots, with ~15 parent-level rule sets. That is well short of the 200 you feared, because silhouette/length/fabric/coverage carry the variation as attributes. Adding "sharara" later = one INSERT, no engine change, no app release.

**Sources:** [Aza Fashions — traditional Indian dresses guide](https://www.azafashions.com/blog/traditional-indian-dresses-for-women-style-guide/) · [ByShree — ethnic bottom wear guide](https://byshree.com/blogs/news/a-comprehensive-guide-to-bottom-wear-in-ethnic-attires) · [Aza — kurta vs kurti](https://www.azafashions.com/blog/what-is-a-kurta/) · [G3 Fashion — saree styles by state](https://g3fashion.com/blog/fashion/saree-style-according-to-state/) · [G3 Fashion — men's ethnic wear types](https://g3fashion.com/blog/fashion/types-of-ethnic-wear-for-men/) · [Wikipedia — Mekhela sador](https://en.wikipedia.org/wiki/Mekhela_sador) · [Wikipedia — Mundum neriyatum](https://en.wikipedia.org/wiki/Mundum_neriyatum) · [Tulsi Silks — saree draping styles](https://tulsisilks.co.in/blogs/types-of-traditional-saree-draping-styles-from-different-states-in-india) · [ODs — dress silhouettes](https://www.odsdesignerclothing.com/en-us/pages/dress-silhouettes) · [The LVLL — dress silhouettes guide](https://www.thelvll.com/blogs/dress-code/dress-silhouettes) · [Medium — men's ethnic wear guide](https://medium.com/@theethnicco1/a-guide-to-traditional-indian-mens-ethnic-wear-styles-and-types-a777b508c8a9)
