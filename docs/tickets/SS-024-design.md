# SS-024 — Footwear Module (Separate Catalogue + Matching) — Design

Architect pass: 2026-08-14 · Branch `feature/SS-024-footwear-module` · cut from `develop`@`f405e41`

---

## 0. Scope restatement (rescope-first)

SS-024 was transcribed from the epics doc on **2026-07-28**, before SS-025, SS-027, SS-034, SS-037 and SS-038 shipped. Those tickets built the occasion registry, the styling-rules pre-filter, the garment-types registry and Engine v2's four-stage pipeline — and in doing so they delivered most of what SS-024 was written to ask for. This pass therefore **verifies each of the four ACs against the actual code first**, and designs only what is genuinely left.

Verified outcome: **AC #1, AC #2 and AC #3 are already fully delivered; AC #4 is delivered on the backend and entirely absent from the UI.** The ticket's own second failure mode — footwear formality mismatch (sneakers-only wardrobe at `wedding_guest`) — is **not** handled anywhere, and is the single most substantive piece of residual scope. The residual work is: one additive backend gap flag, one UI section on the outfit card ("Best footwear for this outfit" + the two nudges), and one India-aware footwear vocabulary hint in the existing Gemini prompt. No migration, no port change, no new screen.

The `[2 pts]` / 6h estimate is **no longer honest**. Re-estimated at **1 pt / ~3h** (§8).

Also settled here, because the ticket explicitly asked for it rather than a silent pick: footwear's `type`/`formality` **does already have a real DB enum** — but at the formality-bucket grain, not the juti/kolhapuri grain. See §3, which closes the ticket's own Technical Note open question and records the correction to the pre-check's premise about *where* that enum lives.

---

## 1. AC-by-AC verification against the current code

Every claim below is `[VERIFIED 2026-08-14]` **by reading the named file at the named line on this branch**. Nothing here is asserted from memory, and nothing is inferred from a test name alone. Where I am inferring runtime behaviour from source rather than from an executed run, it is labelled *inference*.

### AC #2 — "AI suggests footwear alongside every outfit" → **ALREADY MET. No work needed.**

`[VERIFIED 2026-08-14]` Footwear is a first-class assembly slot throughout Engine v2, not a placeholder:

- `backend/services/engine_v2_candidate_search.py:60` — `_ALL_SLOTS = ("top", "bottom", "one_piece", "outerwear", "footwear", "accessory")`.
- `:245` — `footwear_ranked = sorted(grouped["footwear"], key=lambda i: (-footwear_key(i), i.id))`; `:234-238` biases that ranking by `rules.preferred_footwear_categories` with a `+0.2` bonus.
- `:280-281` — footwear is appended to every assembled candidate's `items` when one exists.
- `:302-303` — footwear is one of the slots the expansion **varies one-at-a-time** across its top-N, so a portfolio shows genuinely different shoe choices rather than the same pair five times. Asserted by `backend/tests/test_engine_v2_candidate_search.py:205` (`test_expansion_produces_multiple_distinct_footwear_choices`).
- `backend/services/styling_rules_defaults.py:104-144` — `footwear_required=True` is set on every seeded occasion kind, with `preferred_footwear_categories` authored per kind (e.g. `["footwear_formal"]` for the professional kind, `["footwear_ethnic","footwear_formal"]` for the three ceremony/festival/religious kinds).

This is *more* than the ticket asked for (it asked only that footwear be included; the engine also ranks, varies and occasion-biases it). **Close AC #2 as delivered by SS-027/SS-038. Do not extend `/outfit-suggestions` — the ticket's "endpoint extended to always include a footwear pairing" is already true.**

### AC #3 — "Footwear tagged with a formality level (formal/ethnic/casual/sports)" → **ALREADY MET. No work needed.** (with a correction to where it lives)

`[VERIFIED 2026-08-14]` Formality is encoded in the **category key itself**, and that key is a **real DB enum**:

- `backend/ai/ports/interfaces.py:202-227` — the `WardrobeCategory` Literal, whose own comment records it as "Transcribed verbatim from `supabase/migrations/001_initial.sql` (lines 7-14), the real `wardrobe_category` DB enum — 21 values… The DB write rejects any non-member." It contains `footwear_formal`, `footwear_casual`, `footwear_ethnic`, `footwear_sports` — **exactly** the four levels AC #3 names, no more, no fewer.
- `backend/ai/ports/interfaces.py:255-258` — `category` is validated **strictly** against that enum; an out-of-enum value fails the whole payload. So a footwear item structurally cannot exist without one of the four formality levels.
- `backend/services/styling_rules_defaults.py:65-68` — those four keys additionally carry a numeric `base_formality` (`formal:7, ethnic:6, casual:3, sports:1`) that the engine scores against.
- `mobile/features/wardrobe/wardrobe.constants.ts:89-92` and `backend/tests/test_db_schema.py:84-87` mirror the same four values.

**Correction to the pre-check's premise (stated plainly, as asked).** The formality encoding is **not** in migration `014`'s garment-types registry. `[VERIFIED 2026-08-14]` I read `supabase/migrations/014_garment_types_registry.sql` in full through its seed section (lines 169-327): it seeds 8 parents and their children across `torso_base`/`legs`/`drape`/`torso_mid`/`full_body`/`set` — and **zero rows with `slot = 'feet'`**. `'feet'` appears only once in the whole file, in the `slot` CHECK list at line 55. A case-insensitive grep for `juti|kolhapuri|mojari|sneaker|heel|sandal|loafer|oxford` across `supabase/migrations/` returns **no matches at all**. So `014` reserved a `feet` slot and never populated it.

The conclusion for AC #3 is unchanged (already met), but the mechanism matters for §3's open question and for §6's edge cases, so it is recorded rather than glossed.

### AC #4 — "'Missing footwear' alert if no appropriate footwear exists for the occasion" → **HALF MET. Backend done, UI absent. This is real residual scope.**

The two halves genuinely have different answers:

**Backend half — DONE.** `[VERIFIED 2026-08-14]`
- `backend/services/engine_v2_candidate_search.py:282-283` — `elif rules.footwear_required: gap_flags.append("missing_footwear")`.
- `backend/services/engine_v2_types.py:84-90` — `AssembledCandidate.gap_flags` carries it; its docstring names `missing_footwear` as the worked example.
- `backend/services/engine_v2_candidate_search.py` also records `"footwear"` in `CandidateSearchResult.missing_slots`, asserted at `backend/tests/test_engine_v2_candidate_search.py:272`.
- `backend/services/engine_v2_attribute_scoring.py:94-105` — absent required footwear drives `category_completeness_score`'s component to `0.2`.
- The flag survives to the API and to storage: `mobile/features/outfit-ai/outfit-ai.types.ts:53` (`gap_flags: string[]` on `PortfolioItemResponse`), `:61-68` (`GapReport.missing_slots`), and `supabase/migrations/013_suggestion_impressions.sql:122` (`gap_flags TEXT[] NOT NULL DEFAULT '{}'`).

**UI half — ABSENT.** `[VERIFIED 2026-08-14]` A repo-wide grep for `missing_footwear|gap_flags|gapFlags` across `mobile/` returns **only** the type declarations above, the generated `mobile/types/supabase.ts`, and four test fixtures that set `gap_flags: []`. **No component reads `gap_flags`.** Confirmed by reading the renderer directly: `mobile/features/outfit-ai/components/OutfitCard.tsx` renders the item stack, an occasion badge, a score badge, a reasoning disclosure and accept/reject buttons — and never touches `item.gap_flags`. Likewise `gap_report` is never rendered; `mobile/app/(tabs)/style.tsx:211` passes only `limited_options` down to the deck.

So today: a user with zero footwear gets a correctly-flagged, correctly-down-scored suggestion — and sees **nothing at all** telling them why. The backend already computed the alert AC #4 asks for; nobody displays it. **This is the ticket's main remaining deliverable.**

### AC #1 — "Footwear items display in a separate tab in the wardrobe" → **MET IN SUBSTANCE. Product decision required; recommendation below is: do not build a tab.**

`[VERIFIED 2026-08-14]` A dedicated, persistent, counted footwear view already exists:
- `mobile/features/wardrobe/wardrobe.constants.ts:166-173` — `CATEGORY_FILTER_PILLS` includes `{ value: 'footwear', label: 'Footwear' }`.
- `:137-159` — `CATEGORY_GROUPS` maps all four `footwear_*` categories to the `'footwear'` group.
- `mobile/features/wardrobe/components/CategoryFilterBar.tsx:68-76` — renders it as a **sticky** chip row, each pill labelled with a **live count** (`Footwear (12)`) from `countsByCategoryFilter`, with selected state.
- `mobile/features/wardrobe/wardrobe.store.ts:227,248` — the selection is global Zustand state (`categoryFilter`), so it persists across navigation within a session.

**The trade-off (this is a product call, not a coding one).**

| | Existing "Footwear" filter pill | A dedicated footwear tab |
|---|---|---|
| Reaches a footwear-only view | Yes, one tap | Yes, one tap |
| Live item count visible | Yes, in the pill label | Would need re-implementing |
| Inherits search / sort / grid / upload FAB / free-tier warning | Yes, all of it, for free | No — each must be duplicated or the tab is a worse wardrobe |
| Consistency with `Ethnic` / `Western` / `Accessories` | Yes — footwear is one of four peer groups | **No** — elevates one group above its three peers with no product reason |
| Cost | Zero (shipped in SS-014) | A 5th root tab (today: index/wardrobe/discover/profile), a second wardrobe surface, split state |

**Recommendation: treat AC #1 as met by the filter pill and do not build a separate tab.** The 2026-07 wording said "tab" because at transcription time no wardrobe filtering existed to say otherwise; SS-014 subsequently shipped a strictly better version of the same user goal. Building a real tab now would fragment the wardrobe screen (search, sort, multi-column grid, upload FAB and the free-tier warning all live there) and would demote three peer category groups by implication. Per CLAUDE.md's anti-duplication posture and the rulebook's risk-weighting rule, spending a 5th navigation slot on this is not justified.

**The one genuinely missing piece of AC #1's *intent*** is not a tab — it is that nothing can currently *route a user to* the footwear view. AC #4's nudge needs exactly that. §4 therefore scopes a CTA that sets `categoryFilter` and navigates to the wardrobe — which is the whole of AC #1's residual, and is ~5 lines.

---

## 2. The ticket's two stated failure modes — does Engine v2 already handle them?

### Failure mode A — "user has clothing but zero footwear" → **handled backend-side, invisible to the user.**

`[VERIFIED 2026-08-14]` Covered by AC #4's backend half (§1). The suggestion is not broken and the slot is not empty-but-silent internally: `build()` simply omits the footwear item and appends `missing_footwear`, and `category_completeness_score` drops that component to `0.2` so footwear-less candidates rank below footwear-bearing ones. **The engine already degrades correctly.** What's missing is purely the nudge — §4.2/§4.3.

### Failure mode B — "only sneakers owned, occasion is `wedding_guest`" → **NOT handled. This is a live defect against the ticket's own wording.**

`[VERIFIED 2026-08-14]` Trace the sneakers-only + ceremony-kind case through the current code:

1. `engine_v2_candidate_search.py:234-245` — `preferred_footwear_categories` only awards a `+0.2` **ranking bonus**. Non-preferred footwear is **never excluded**; with sneakers as the only footwear, `footwear_ranked` is `[sneakers]` regardless.
2. `:280-281` — sneakers are attached to the candidate.
3. `:282-283` — the `missing_footwear` flag is in the `elif` branch, reached **only when `footwear is None`**. Footwear is present, so **no gap flag of any kind is recorded.**
4. `engine_v2_attribute_scoring.py:96-103` — the only consequence is `components.append(0.7)` instead of `1.0`, i.e. a `0.3` penalty on **one component** of `category_completeness_score`, which is itself **one weighted rule among many** in the final score.

*Inference (from source, not from an executed run):* that penalty is far too dilute to change the outcome when sneakers are the user's only shoes — there is nothing to outrank. The user is shown **sneakers with a `wedding_guest` outfit and no signal whatsoever that anything is off**. That is precisely the "forced mismatched suggestion" the ticket says must never happen.

This is a genuine, currently-shipping gap that no later ticket closed, and it is the strongest reason SS-024 still deserves to exist. §4.1 fixes it — additively, in the same three lines of `build()` that already produce `missing_footwear`.

Note this is a *sibling* of `BL-129` (which records that outerwear attaches opportunistically to any occasion and can be stylistically incongruous), but it is not the same row: `BL-129` is about a ranking/appropriateness concern with no flag, and names Engine v2's register-coherence scoring as its owner. Footwear's case is worse in one specific way — the engine already **knows** the occasion's preferred footwear categories and already **computes** the mismatch, and simply throws that knowledge away instead of surfacing it. We are not inventing a judgment; we are recording one the engine already makes.

**A note on why register-coherence scoring does not already cover this.** `[VERIFIED 2026-08-14]` `engine_v2_attribute_scoring.py:157-174`'s `register_coherence_score` only scores a pair when **both** items resolve through `garment_lookup`. Since migration `014` seeded no `feet`-slot rows (§1, AC #3), and `garment_registry_adapter.py:107-121` returns `None` for any unresolvable key, **footwear resolves to `None` and contributes no register signal at all**. Its unresolved-pair branch is a graceful degrade (`:142-143` — `continue`, excluded from the mean, not scored `0`), so this is not a crash or a wrong score — it is simply *no* signal. This is a footwear-specific instance of the already-logged **`BL-132`** ("`volume_balance`/`register_coherence` scoring is architecturally correct but 100% live-inert until Wave 2's taxonomy migration — no live `wardrobe_items.category` value currently resolves through `garment_types`"). **Not a new backlog row**; §7 records the footwear instance against `BL-132`.

---

## 3. Closing the ticket's own Technical Note open question (enum vs. `BL-064` free-text)

The ticket asks the Developer to "decide explicitly whether footwear type gets a real DB enum (jutis/kolhapuri are India-specific values worth getting right) or joins the same deferred-taxonomy posture." **It is already decided, and the answer is "both, at two different grains." Do not re-litigate it, and do not add a new enum.**

| Grain | Where it lives | Posture | Status |
|---|---|---|---|
| **Formality bucket** — `footwear_formal` / `footwear_casual` / `footwear_ethnic` / `footwear_sports` | `wardrobe_category` **DB enum**, `supabase/migrations/001_initial.sql` | Strict. Out-of-enum fails the payload (`ai/ports/interfaces.py:255-258`) | **Settled — a real DB enum already exists.** This is what AC #3 asks for and it is done. |
| **Granular type** — juti / kolhapuri / mojari / heels / flats / sneakers / sandals / loafers | `wardrobe_items.subcategory`, free `TEXT` (`GarmentTags.subcategory: str \| None`) | Lenient, Gemini-supplied, no enum | **Joins `BL-064`'s deferred-taxonomy posture** — same shape as `pattern`/`fabric` before SS-036 registered them. |

**Why this split is right, not just convenient.** The enum exists at exactly the grain the *engine consumes*: `preferred_footwear_categories` (`styling_rules_defaults.py:117-144`) and `CATEGORY_BASE_FORMALITY` (`:65-68`) both key off the formality bucket, never off "juti vs. mojari". Nothing in Engine v2 reads `subcategory`. Adding a juti/kolhapuri DB enum today would create a controlled vocabulary with **zero consumers** and a migration cost, while SS-036 already established the correct precedent for this class of vocabulary: a **registry table with alias normalisation** (as it did for `patterns`/`fabrics` in migration `016`), not a Postgres enum. If a future ticket needs granular footwear types (a filter, a facet, a stylist rule), the right move is a `footwear_types` registry row set in that ticket, following SS-036's shape — **not** an enum bolted on here.

**What SS-024 does do about the granular grain:** improve the *quality* of the free-text values without constraining them — §4.4 adds an India-aware footwear vocabulary hint to the existing prompt, exactly the "guiding vocabulary, no hard reject" posture `BL-064` itself records as correct. This is the cheapest thing that makes jutis and kolhapuris come back as `juti`/`kolhapuri` rather than `shoes`, and it is what makes a future registry seed cheap to author from real data.

`BL-064` is therefore **touched and advanced, not resolved** — see §7.

---

## 4. Residual scope — files to create/modify

Four units. No migration, no new port, no new screen, no change to any existing function signature.

### 4.1 Backend — `footwear_formality_mismatch` gap flag (fixes failure mode B)

**Modify** `backend/services/engine_v2_candidate_search.py` — inside the existing nested `build()` (currently lines 273-283). `preferred_footwear` is **already in scope** (computed at `:234`), so this needs no new plumbing:

```python
if footwear is not None:
    items.append(footwear)
    if (
        rules.footwear_required
        and preferred_footwear
        and footwear.category not in preferred_footwear
    ):
        gap_flags.append("footwear_formality_mismatch")
elif rules.footwear_required:
    gap_flags.append("missing_footwear")
```

Concrete decisions, so the Developer does not have to guess:
- **Flag string is exactly `footwear_formality_mismatch`** — `snake_case`, matching `missing_footwear`/`missing_outerwear`.
- **Gated on `rules.footwear_required and preferred_footwear`**, mirroring `engine_v2_attribute_scoring.py:94-103`'s existing gate exactly. No new semantics: the flag fires in precisely the situation where that code already applies its `0.7` penalty. An occasion that expresses no footwear preference never produces this flag.
- **`missing_footwear` and `footwear_formality_mismatch` are mutually exclusive** by construction (different branches of the same `if`). Assert this in a test — it bounds the prompt-payload growth (§4.5).
- **Scoring is NOT changed.** The existing `0.7` component stays exactly as-is. This unit only *surfaces* a judgment the engine already makes. Changing weights would put SS-024 on Engine v2's calibration surface (`BL-077`/`BL-145` territory) for no acceptance-criteria benefit.
- **No exclusion.** Mismatched footwear is still suggested — the ticket says "surface this as a gap/nudge", and suppressing the only shoes a user owns would produce a *worse* outcome (a barefoot outfit) than a flagged one.
- **No migration.** `[VERIFIED 2026-08-14]` `supabase/migrations/013_suggestion_impressions.sql:122` — `gap_flags TEXT[] NOT NULL DEFAULT '{}'`, **no `CHECK` constraint**. A new member value is accepted by the existing column as-is. This is the single fact that keeps SS-024 off the schema surface; the Developer must not add a migration.

### 4.2 Mobile — "Best footwear for this outfit" section

**Create** `mobile/features/outfit-ai/components/FootwearSection.tsx`.

`[VERIFIED 2026-08-14]` No backend response change is needed to identify the footwear item. `engine_v2_attribute_scoring.py:332` builds `category_labels={item.id: item.category ...}` — the **raw category enum value** (e.g. `footwear_ethnic`), and `PortfolioItemResponse.category_labels` already carries it to the client (`outfit-ai.types.ts:48`). The component resolves the footwear item by reusing the existing, already-exported mapping — **not** by string-prefix matching:

```ts
import { CATEGORY_GROUPS } from '../../wardrobe/wardrobe.constants';
// footwearItemId = the item id whose category maps to CATEGORY_GROUPS[...] === 'footwear'
```

Rendering rules (all three states, per CLAUDE.md):
1. **Footwear present, no mismatch flag** — heading + that item's thumbnail, reusing `OutfitItemStack` with a single-element `itemIds` array. Never a second thumbnail implementation.
2. **`gap_flags` contains `missing_footwear`** — the nudge (§4.3), no thumbnail.
3. **`gap_flags` contains `footwear_formality_mismatch`** — the thumbnail **plus** the mismatch nudge beneath it. The pair is still shown; the caveat sits with it.
4. **Neither flag and no footwear item resolvable** (occasion with `footwear_required=False`, or an item deleted between suggestion and render) — **render nothing at all**. An empty labelled section is the "broken/empty suggestion slot" the ticket forbids.

**Modify** `mobile/features/outfit-ai/components/OutfitCard.tsx` — insert `<FootwearSection item={item} />` between `<OutfitItemStack …>` (line 39) and the badge row (line 41). Props: pass the whole `item: PortfolioItemResponse` (the component needs `item_ids`, `category_labels` and `gap_flags`); no prop drilling beyond one level.

### 4.3 Mobile — the two nudges and the route-to-footwear CTA (AC #4's UI half + AC #1's residual)

**Modify** `mobile/features/outfit-ai/outfit-ai.constants.ts` — add the copy block. These strings are the Architect's own authored copy (no design doc pins them); flagged as such so they are not mistaken for transcribed values:

```ts
export const FOOTWEAR_SECTION_HEADING = 'Best footwear for this outfit';
export const MISSING_FOOTWEAR_HEADING = 'No footwear in your wardrobe yet';
export const MISSING_FOOTWEAR_SUBTEXT =
  'Add a pair and your outfits will be complete.';
export const FOOTWEAR_MISMATCH_HEADING = 'These are a casual match';
export const FOOTWEAR_MISMATCH_SUBTEXT =
  'This is the only footwear you own for this occasion. Formal or ethnic footwear would suit it better.';
export const ADD_FOOTWEAR_CTA = 'Add footwear';
```

**The CTA (this is all of AC #1's residual).** No new route, no URL param, no fifth tab. `categoryFilter` is already global Zustand state, so:

```ts
setCategoryFilter('footwear');   // features/wardrobe/wardrobe.store.ts
router.push('/(tabs)/wardrobe'); // Expo Router, per CLAUDE.md
```

The user lands on the wardrobe with the Footwear pill pre-selected — the empty-category state (`NO_ITEMS_IN_CATEGORY_HEADING`) and the upload FAB are both already there. Wrap the handler in `useCallback` (CLAUDE.md). Cross-feature store import is acceptable here and already precedented (`OutfitItemStack.tsx:5` imports `wardrobe.queries`); no Supabase call is added.

*Known minor limitation (accepted, not silently ignored):* on web, a hard refresh after this navigation loses the pre-selected filter, since it lives in memory rather than the URL. Acceptable for MVP — the user is already on the right screen. A URL-param-hydrated filter is the fuller fix and is logged as `BL-157` (§7) rather than built here.

### 4.4 Backend — India-aware footwear vocabulary in the existing Gemini prompt

**Modify** `backend/ai/adapters/gemini_vision_adapter.py`'s `_TAXONOMY_PROMPT_TEMPLATE`, the `subcategory` line only (currently line 100):

```
  "subcategory": a short free-text label (e.g. "straight-fit kurta"), or null
    -- if the item is footwear, prefer one of [juti, mojari, kolhapuri,
    sandal, sneaker, sports_shoe, heel, wedge, flat, ballerina, loafer,
    oxford, brogue, derby, boot, flip_flop, slipper] or another short label
    if none of those fit,
```

**Architecturally important — why this is a *vocabulary hint*, not a "footwear-specific prompt variant".** The ticket's Description asks for "a footwear-specific Gemini prompt". `[VERIFIED 2026-08-14]` that is **not implementable as written**: `IVisionProvider.tag_garment(self, image_bytes: bytes)` (`ai/ports/interfaces.py:367`) takes the image and nothing else, and the upload flow passes no category hint — **the category is the prompt's own output**, so nothing knows an item is footwear until after the single tagging pass has run. Selecting a footwear prompt up-front would require either a port signature change (violating the Open/Closed rule CLAUDE.md states for ports, and which SS-025 went out of its way to honour via constructor injection) or a second billed Gemini call per item.

Enriching the one prompt achieves the ticket's actual intent — good India-specific footwear labels — at **zero additional cost, zero API calls and zero interface churn**. Recommended and designed; the literal "separate prompt" reading is explicitly rejected with the reason recorded here.

Vocabulary sourcing: `juti`/`mojari`/`kolhapuri` are the ticket's own named India-specific values plus `mojari` (the common Rajasthani/North-Indian sibling of `juti`); the rest are the ticket's list (heels/flats/sneakers/sandals/loafers) plus ordinary siblings. Values are `lowercase_underscore`, matching how every other free-text vocabulary in this prompt is shaped. **No hard rejection** — `GarmentTags.subcategory` stays `str | None` (`ai/ports/interfaces.py:283`), per `BL-064`'s recorded posture.

*Unverifiable claim, stated plainly as required.* I have **no web-fetch tool in this pass**, exactly as recorded for SS-022's Architect pass. I therefore **could not verify** anything about Gemini's current vision API behaviour, `gemini-3.5-flash-lite`'s live availability, or how it handles a longer enumerated vocabulary in a prompt. What I *can* verify is repo-local: `gemini_vision_adapter.py:70-73` carries a `[VERIFIED 2026-07-25]` note from a live call. This change adds ~60 tokens of prompt text to an existing, working call and changes no SDK surface, so *(inference, not verified)* it should not alter API behaviour — but the Developer must confirm the model still returns valid JSON, either by an existing adapter test with a fake client or by a live call, and record which.

### 4.5 `BL-130` — prompt-payload budget must be re-measured, not assumed

`[VERIFIED 2026-08-14]` `gap_flags` is rendered into the **narration** prompt payload (`backend/tests/test_styling_rules_engine.py:103-106` asserts `rendered["gap_flags"] == ["missing_footwear"]`), so §4.1's new flag directly grows the payload `BL-130` budgets. `BL-130` records a measured worst case of **595 chars against a 700-char budget** for a 6-item ceremony candidate.

`"footwear_formality_mismatch"` is 27 characters, ~31 with JSON quoting and a comma. Since the two footwear flags are mutually exclusive (§4.1), the growth is bounded at one flag. *Inference:* 595 + ~31 ≈ 626, still inside 700. **This must be re-measured by an actual test run, not accepted from this arithmetic** — see §5. This is `BL-130`'s stated re-verification trigger firing exactly as the row anticipated.

---

## 5. Test plan

Only the residual scope is tested. **Do not add tests re-asserting AC #2/#3** — they are already covered (`test_engine_v2_candidate_search.py:205`, `test_engine_v2_eligibility.py:188`, `test_db_schema.py:84-87`, `test_styling_rules_defaults.py:45`). Re-testing shipped behaviour under a new ticket's name is exactly the duplication CLAUDE.md's "distill once" rule warns about.

### Backend — `backend/tests/test_engine_v2_candidate_search.py` (extend)

- `test_mismatched_footwear_sets_formality_mismatch_flag` — occasion with `footwear_required=True, preferred_footwear_categories=["footwear_ethnic","footwear_formal"]`, wardrobe's only footwear is `footwear_sports`: every assembled candidate carries `"footwear_formality_mismatch"` in `gap_flags`, **and the sneakers are still present in `items`** (asserts "surface as a gap, never suppress" — the ticket's literal failure-mode wording).
- `test_preferred_footwear_sets_no_gap_flag` — same occasion, wardrobe has `footwear_ethnic`: `gap_flags` is empty. Guards against a false-positive nudge on a correct outfit.
- `test_footwear_gap_flags_are_mutually_exclusive` — no candidate ever carries both `missing_footwear` and `footwear_formality_mismatch`. This is the assertion §4.5's payload bound rests on.
- `test_no_mismatch_flag_when_occasion_has_no_preferred_footwear` — `preferred_footwear_categories` empty/`None` and any footwear owned: no flag. Guards the `and preferred_footwear` gate.
- `test_no_mismatch_flag_when_footwear_not_required` — `footwear_required=False` with a preference list set: no flag. Guards the other half of the gate.

### Backend — `backend/tests/test_styling_rules_engine.py` (extend, `BL-130`)

- `test_render_candidate_for_prompt_budget_with_footwear_mismatch_flag` — build the same worst-case 6-item ceremony candidate `test_render_candidate_for_prompt_stays_within_budget_for_max_size_candidate` (`:67`) uses, add `gap_flags=["footwear_formality_mismatch"]`, assert it stays within the **700-char** budget that test already establishes. **The measured number must be recorded in the test docstring**, matching how SS-037's Developer recorded `595` — so `BL-130`'s next re-verification has a real datum rather than an estimate.

### Backend — `backend/tests/test_gemini_vision_adapter.py` (extend; create only if absent)

- `test_prompt_includes_india_footwear_vocabulary` — the rendered prompt contains `juti`, `mojari` and `kolhapuri`. Cheap regression pin: the India-specific values are the whole point of §4.4 and are the first thing a future prompt edit would drop.
- `test_footwear_subcategory_out_of_vocabulary_is_accepted` — `GarmentTags(category="footwear_ethnic", subcategory="peshawari_chappal", …)` validates successfully. Pins `BL-064`'s lenient posture against a future strict-validation regression.

### Mobile — `mobile/__tests__/features/outfit-ai/components/FootwearSection.test.tsx` (create)

- renders the heading and exactly one thumbnail when the candidate contains a `footwear_*` item and `gap_flags` is empty.
- renders `MISSING_FOOTWEAR_HEADING` + `ADD_FOOTWEAR_CTA` and **no** thumbnail when `gap_flags` contains `missing_footwear`.
- renders the thumbnail **and** `FOOTWEAR_MISMATCH_HEADING` when `gap_flags` contains `footwear_formality_mismatch` (asserts the pair is still shown alongside the caveat).
- renders **nothing** (`toBeNull()` on the section testID) when there is no footwear item and no footwear gap flag — the forbidden empty-slot case.
- renders **nothing** when `category_labels` is `{}` (an item deleted between suggestion and render) — no crash, no orphan heading.
- pressing `ADD_FOOTWEAR_CTA` calls `setCategoryFilter` with `'footwear'` **and** `router.push` with the wardrobe route (both mocked). Asserts AC #1's residual end-to-end at the unit level.

### Mobile — `mobile/__tests__/features/outfit-ai/components/OutfitCard.test.tsx` (extend)

- an `OutfitCard` whose item has `gap_flags: ['missing_footwear']` renders the footwear nudge — pins the wiring, since the existing fixture at `:28` sets `gap_flags: []` and would pass whether or not the section was ever mounted.

---

## 6. Edge cases

Carried forward from the ticket, plus what this pass found in the current codebase.

**From the ticket:**
1. **Clothing but zero footwear** — `missing_footwear` already flagged backend-side; §4.2 case 2 renders the nudge instead of an empty slot. Covered.
2. **Footwear formality mismatch** — §4.1 + §4.2 case 3. Shown *with* a caveat, never suppressed and never silently forced. Covered.

**New, found during this pass:**
3. **Occasion with `footwear_required=False`** — no footwear item, no flag. §4.2 case 4 renders nothing. The section must not appear as an empty labelled block.
4. **Footwear item deleted between suggestion and render** — `category_labels` may name an id that no longer resolves to an image. `OutfitItemStack` already handles this (`ITEM_NO_LONGER_IN_WARDROBE_COPY`, `:49-61`); reusing it inherits the behaviour for free. Do not reimplement.
5. **Multiple footwear items in one candidate** — *(inference)* not producible by the current assembler (`build()` appends at most one), but the component must not assume it. Take the first `footwear`-group entry deterministically; never render two thumbnails under a singular heading.
6. **Both footwear flags present** — impossible by construction (§4.1), but §4.2's render order must still be deterministic if a future change breaks that: `missing_footwear` wins (no thumbnail exists to show).
7. **Hindi rationale beside English nudge copy** — `rationale_language` can be `'hi'` (`outfit-ai.types.ts:9,51`), and the footwear nudges sit directly above the rationale. New hardcoded English strings will therefore appear adjacent to Hindi text. This is exactly `BL-154`'s subject (§7); accepted for MVP, logged, not solved here.
8. **Footwear never resolves through `garment_types`** — so it contributes no `register_coherence`/`volume_balance` signal (§2). Degrades to "no signal", not a wrong score. Recorded against `BL-132`/new `BL-156`.
9. **Free-tier 50-item cap** — the `ADD_FOOTWEAR_CTA` can land a user on a wardrobe that is already at `FREE_TIER_WARDROBE_CAP`. The existing wardrobe screen already owns that messaging (`WARDROBE_LIMIT_MESSAGE`, `FREE_TIER_WARNING_THRESHOLD`); the CTA must not duplicate or pre-empt it.
10. **Out-of-vocabulary footwear subcategory** (e.g. `peshawari_chappal`) — accepted, never rejected. Pinned by a test (§5).

---

## 7. Backlog

### Active rows scanned (tags `ai` / `infra` / `schema` / `test`)

| Row | Verdict for SS-024 |
|---|---|
| **`BL-064`** (ai) — `pattern`/`fabric` free TEXT, no controlled vocabulary | **Touched and advanced, NOT resolved.** §3 settles footwear's side of the question the ticket named it for: the formality grain already has a real DB enum (`wardrobe_category`), the granular juti/kolhapuri grain stays free-text `subcategory` under this row's posture. §4.4 improves the *values* without constraining them — the same "guiding vocabulary, no hard reject" this row records as correct. This row's own remaining subject (`color_primary`/`color_secondary` binning) is untouched. |
| **`BL-130`** (test) — prompt-payload size budget | **Touched, needs re-measurement.** §4.5: `footwear_formality_mismatch` (27 chars) is rendered into the narration payload. §5 requires a real measured number in the new test's docstring. This is the row's own stated trigger firing. Stays Active. |
| **`BL-126`** (ai) — `patterns` has no attribute columns | **Unaffected.** SS-024 adds no pattern scoring and reads no pattern attributes. |
| **`BL-127`** (infra) — no registry-driven UI/labels for pattern/fabric | **Unaffected.** `FootwearSection` displays a thumbnail and copy, never a raw `pattern`/`fabric` value. |
| **`BL-116`** (schema) — garment-set item-level consumption undesigned | **Unaffected.** Sets occupy the `set`/`torso`/`legs` slots; footwear is an independent slot. No interaction. |
| **`BL-125`** (schema-adjacent) — silk/khadi `NULL season_affinity` | **Unaffected.** SS-024 touches no `fabrics` row and no fabric×weather scoring. |
| **`BL-132`** (ai) — `volume_balance`/`register_coherence` live-inert | **Touched, NOT resolved.** §2 records the footwear-specific instance: footwear contributes no register signal, degrading gracefully. New `BL-156` records the *additional* footwear-only blocker this row does not cover. |
| **`BL-129`** (ai) — opportunistic outerwear attachment, no flag | **Adjacent sibling, NOT resolved.** SS-024 fixes the footwear analogue only, and only by flagging (not by scoring). The outerwear half stays with that row. |
| **`BL-154`** (infra) — no i18n layer in `mobile/` | **Touched, compounds, NOT resolved.** §6 edge case 7: SS-024 adds six more hardcoded English strings directly above rationales that can render in Hindi. Same accepted-for-MVP posture; the row gets worse, not better. |

### Rows to append to **Active** (Source: `SS-024 / Architect`, 2026-08-14)

- **`BL-156`** (`schema`) — *Migration `014`'s `garment_types` registry reserves the `feet` slot but seeds zero `feet` rows, so footwear can never resolve through the registry even after Wave 2's taxonomy migration.* `[VERIFIED 2026-08-14]` `014_garment_types_registry.sql` seeds 8 parents + children across `torso_base`/`legs`/`drape`/`torso_mid`/`full_body`/`set`; `'feet'` appears only in the `slot` CHECK (line 55), and a case-insensitive grep for `juti|kolhapuri|mojari|sneaker|heel|sandal|loafer|oxford` across `supabase/migrations/` returns no matches. This is a **second, independent** blocker beyond `BL-132`: `BL-132` says nothing resolves *yet* because live `wardrobe_items.category` values are the old 21-value enum rather than registry keys — but for footwear there would be nothing to resolve *to* even once that mapping exists. Consequence today: footwear contributes no `register_coherence`/`volume_balance` signal (graceful "no signal", not a wrong score). Whoever owns Wave 2's taxonomy migration must seed `feet`-slot rows or knowingly accept footwear as permanently registry-invisible. Natural pairing: a `footwear_types` registry in SS-036's shape, which is also `BL-064`'s recommended answer for the granular grain (§3).
- **`BL-157`** (`infra`) — *Wardrobe `categoryFilter` is in-memory Zustand only; no URL-param hydration, so any deep link or web refresh loses it.* Surfaced by SS-024's `ADD_FOOTWEAR_CTA` (§4.3), which sets the filter then navigates — correct within a session, lost on a web hard refresh. Not blocking (the user still lands on the right screen), but the first real cross-screen consumer of the filter makes it visible. Natural owner: whichever ticket next needs a shareable or deep-linkable wardrobe view.
- **`BL-158`** (`ai`) — *`footwear_formality_mismatch` is a bare flag string, so the nudge copy cannot name which footwear kinds the occasion actually prefers.* The engine knows `preferred_footwear_categories` (`styling_rules_defaults.py:117-144`) but the gap-flag channel is `TEXT[]` of bare strings, so §4.3's copy has to hardcode "Formal or ethnic footwear" — correct for the seeded ceremony kinds, but it would drift if an occasion's preference list is ever re-authored. A structured gap payload (flag + parameters) would fix this class of copy for `missing_outerwear` too. Deliberately not built here: it changes the `gap_flags` column's shape, which would put a `Risk: low` ticket onto the schema surface for a copy nicety.

**No existing row is resolved by this ticket.**

---

## 8. Re-estimate (the ticket's `[2 pts]` / 6h is no longer honest)

| Unit | Effort |
|---|---|
| §4.1 backend gap flag (5 lines, in-scope variables already present) | ~20 min |
| §4.2/§4.3 `FootwearSection` + copy + CTA wiring | ~1h |
| §4.4 prompt vocabulary line | ~10 min |
| §5 tests (5 backend + 1 budget + 2 adapter + 7 mobile) | ~1h 15m |
| Lint/type/test/QA loop | ~30m |

**Re-estimate: `[1 pt]` / ~3h**, down from `[2 pts]` / 6h. The original estimate priced building a wardrobe tab, a category, a prompt variant and a suggestion-endpoint extension. Three of those four are already shipped; the fourth is not implementable as literally worded (§4.4). **The Developer should not spend 6h here — if the work is taking that long, something has been misread as in-scope.**

Recommended raw-ticket amendments (for whoever next edits `docs/tickets/raw/SS-024.md`; I have no `Edit` on it in this mode): points `2 → 1`, est `6h → 3h`, add `Risk: low`, and mark AC #1/#2/#3 as delivered with the references in §1.

---

## 9. Open questions / blockers

1. **AC #1 needs a product decision (§1).** My recommendation is: no separate tab; the existing `Footwear (N)` filter pill satisfies the intent, and the residual is only the routing CTA. **This is the one thing a human should actively agree or disagree with** — if the answer is "build a real tab anyway", the estimate goes back up and §4.3 changes substantially. Everything else in this design is a verification result, not a judgment call.
2. **Nothing blocks the Developer.** SS-014 and SS-020 (the ticket's stated dependencies) are both merged; Engine v2, the occasion registry and the outfit card all exist on `develop`. There is no deferred external dependency here — unlike, say, an auth/SMS ticket.
3. **Gemini API behaviour is unverified (§4.4).** No web-fetch tool in this pass (same limitation recorded for SS-022's Architect pass). The prompt change is repo-local and additive, but the Developer must confirm the tagging call still returns valid JSON and record whether that was a fake-client test or a live call.
4. **The mismatch copy is generic by design** (`BL-158`). If a human wants occasion-specific wording ("kolhapuris or juttis would suit a wedding better"), that needs a structured gap payload and becomes a schema-touching ticket — deliberately out of scope.
5. **No conflict found between the ticket's ACs and CLAUDE.md**, other than the "separate tab" wording (question 1) and the "footwear-specific prompt" wording, which conflicts with CLAUDE.md's Open/Closed rule for ports and is resolved in §4.4 with the reasoning recorded rather than silently reinterpreted.

---

**Verdict:** `Risk: low` — no migration (`gap_flags TEXT[]` has no `CHECK`, `[VERIFIED 2026-08-14]`), no auth/payments/RLS/secrets, no port or interface signature change, and no schema surface; the entire residual is one additive gap-flag string, one additive UI section, and one prompt vocabulary line, every part of which is reversible by revert. Fast lane per `.claude/skills/ticket/SKILL.md` — with the single caveat that §9's AC #1 product decision is worth a human's explicit nod at the PR.
