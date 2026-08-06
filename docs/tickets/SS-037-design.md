# SS-037 — Design: SS-027 v0 Fix Pass: Expressibility Bugs

## Scope restatement

SS-027 shipped a deterministic, pure-Python styling rules pre-filter (`backend/services/styling_rules_engine.py` + `styling_rules_defaults.py` + `styling_rules_types.py`) with three known holes named in its own PR body. This ticket closes the half of those holes that change *which* outfits are even expressible, leaving ranking-quality issues to Engine v2: (1) the `wedding_guest`-never-white guard silently lets through any item whose `color_primary` is a named/unparsable string (e.g. the literal `"white"`) instead of a valid hex, because the parser's `None` return is currently treated as "not white" rather than "unknown, could be white"; (2) `ranked_slots["outerwear"]` is computed every call and then thrown away — no candidate can ever include a jacket/layer even when the wardrobe has one; (3) `ethnic_dupatta` is mapped to the `accessory` slot but no occasion kind's `preferred_accessory_categories` lists it, so a dupatta can never attach to any ethnic outfit, and the assembly loop only ever attaches a single accessory total. All three fixes are pure in-memory Python — no schema, no network, no new consumer (the only future caller is SS-020, which doesn't exist yet) — so nothing here is externally reachable until SS-020 wires this engine in.

## Files to create/modify

No new files. All changes are to SS-027's existing surface:

- `backend/services/styling_rules_engine.py` — `_item_is_hard_excluded_white` (Bug 1), the assembly loop inside `generate_candidates` (Bugs 2 and 3), `_category_completeness_score` (Bug 2), module docstring (AC #6: name the deliberately-unfixed gaps).
- `backend/services/styling_rules_defaults.py` — `DEFAULT_STYLING_RULES_BY_KIND`'s `ceremony`/`festival`/`religious` entries (Bug 3: add `ethnic_dupatta` to `preferred_accessory_categories`); an explanatory comment near it (Bug 2: document that no kind sets `outerwear_required` yet, deliberately).
- `backend/services/styling_rules_types.py` — `StylingRulesOverride`: add `outerwear_required: bool | None = None` (Bug 2 — new field, mirrors `footwear_required`; no DB/migration impact since `occasions.styling_rules` is JSONB and `parse_lenient`/`_resolve_styling_rules` already handle unknown/absent keys generically).
- `backend/tests/test_styling_rules_engine.py` — new tests for all three bugs (see Test plan).
- `backend/tests/test_styling_rules_defaults.py` — new test(s) for the Bug 3 data change.
- `backend/tests/test_styling_rules_properties.py` — extend/add a property test covering named/unparsable colours at `wedding_guest`.

## Concrete values to use, not invent

Current line numbers were re-verified against this worktree's `develop`-derived copy of the files (not re-derived from memory or the ticket's own citations, which drift slightly — noted per-item below). All four functions the orchestrator asked me to check are addressed; two of the four need no code change, and that's a deliberate call, justified below.

### Bug 1 — named-colour white guard (fail closed)

Confirmed current line ranges: `_hex_to_hsv` 461-476, `_is_near_white` 479-486, `_item_is_hard_excluded_white` 489-492, `_hue_distance_score` 495-519 (unparsable fallback at line 506). These match the ticket's citations almost exactly (ticket said 461-476/479-486/489-492/`:506` — all exact) except `styling_rules_defaults.py`'s three `preferred_accessory_categories=["accessory_jewellery"]` lines, which the ticket cites as 123/130/135 but are actually **122/129/136** in this worktree — a one-line-per-block drift, not a structural change; use the current numbers.

**`_hex_to_hsv` and `_is_near_white`: NO code change.** Both already have the right contract (never raise; `None`/`False` on unparsable input) and are reused by other callers (`_hue_distance_score`, `_item_is_hard_excluded_white`) whose needs differ — conflating "unparsable" into `_is_near_white`'s own return value would be wrong, since "cannot parse" and "definitely not white" are different facts that only the *caller* can decide how to treat.

**`_item_is_hard_excluded_white`: this is the fix.** It is only ever invoked from `generate_candidates` inside the `if "white" in effective_excluded:` block (line 96-99) — i.e. only when the occasion already has an active hard colour exclusion. Flip its handling of an unparsable colour from "assume safe, keep it" to "cannot prove it isn't white, exclude it":

```python
def _item_is_hard_excluded_white(item: WardrobeItemInput) -> bool:
    """Fails CLOSED, not open (SS-037): an item whose colour cannot be
    parsed as 3/6-digit hex -- a named colour such as "white", "off
    white", "ivory", or any other unparsable string -- is excluded
    rather than silently passed through. This function is only ever
    called when the occasion already applies a hard colour exclusion
    (see generate_candidates's "white" in effective_excluded gate), so
    an unknown colour here means "cannot rule out white," not "assume
    not white." A hex colour is still excluded only by the real
    near-white HSV test."""
    if item.color_primary is None:
        return False
    if _hex_to_hsv(item.color_primary) is None:
        return True
    return _is_near_white(item.color_primary)
```

This alone satisfies the AC's literal example: a `wedding_guest` request against a wardrobe of items tagged `color_primary: "white"` now yields zero candidates, because every hero-slot item is hard-excluded and no base can be assembled (same "structurally zero candidates" mechanism as the existing hex-white test already proves in `test_wedding_guest_excludes_all_white_hero_candidates`).

**`_hue_distance_score`: deliberately NOT changed.** Its flat `0.75` fallback for a pair where either side is unparsable is a *general colour-harmony scoring* concern, not the hard-exclusion guard — it fires for any occasion, not just ones with a hard colour exclusion, and "excluding" doesn't even make sense for a pairwise score (there's nothing to exclude the candidate *from*, only a number to assign). Fixing this properly needs a hex→colour-family binning decision (how many families, what boundaries) — exactly the work `BL-064`/`BL-079`'s still-open colour half describes, and exactly the "partial named-colour map" the raw ticket says to prefer failing-closed over. Leaving it as a documented neutral fallback is the correct, minimal-scope call; state this explicitly in the module docstring (AC #6) rather than silently.

**Confirming the "prefer fail-closed over a partial map" call is right:** a hand-rolled map would need to cover at minimum `white`/`off white`/`ivory`/`cream`/`eggshell`/`beige`/`ecru`/`snow` before it stopped being a trap for the next unlisted synonym, and every one of those needs the same cream/ivory-at-wedding-guest cultural judgment call the ticket's own edge case says not to make here (see `BL-111`). Fail-closed needs zero vocabulary and is strictly safer in the one direction that matters (never suggests white for `wedding_guest`) at the cost of being maximally conservative for any occasion with a hard colour exclusion and a genuinely-non-white named colour (e.g. a hypothetical future `excluded_color_families: ["black"]` occasion would now also exclude an item literally tagged `"red"`, if `"red"` isn't valid hex). That's the correct trade for this ticket's stated AC and is explicitly scoped in the Edge Cases below.

### Bug 2 — outerwear assembly

Confirmed: `generate_candidates` ranks all six slots at line 119 (`ranked_slots = {slot: _rank_within_slot(...) for slot in _ALL_SLOTS}`, `_ALL_SLOTS` includes `"outerwear"`, line 63); `_build_base_combinations` (341-352) correctly excludes `outerwear` from bases (a layer is not a base — no change needed there); the assembly loop (135-159) never reads `ranked_slots["outerwear"]`; `_category_completeness_score` (419-441) only ever scores footwear presence.

**New field** in `styling_rules_types.py`'s `StylingRulesOverride`, placed after `footwear_required`:

```python
outerwear_required: bool | None = None
```

No migration needed — `occasions.styling_rules` is `JSONB`, `parse_lenient` already ignores unknown keys and treats an absent key as `None`, and `_resolve_styling_rules`'s merge loop iterates `StylingRulesOverride.model_fields` generically, so this field is wired end-to-end for free.

**`styling_rules_defaults.py`**: do **not** set `outerwear_required=True` on any of the 9 kind defaults. Deciding which occasion kinds genuinely "expect a layer" (`travel`? `professional` in a cold-weather context?) is real product/stylist judgment this ticket should not invent wholesale — same posture `BL-097` already takes toward authoring real per-occasion `styling_rules` content. Add a one-line comment next to `DEFAULT_STYLING_RULES_BY_KIND` recording this is deliberate, not an oversight, and log it to the backlog (see Backlog logging below) so it isn't silently forgotten.

**Assembly loop fix** — insert immediately after the existing footwear `if`/`elif` block (after line ~147), before the accessory block:

```python
outerwear_options = ranked_slots["outerwear"]
if outerwear_options:
    # Mirrors the footwear pattern directly above: attach the top-ranked
    # item whenever the wardrobe has one, unconditionally -- exactly like
    # footwear is attached regardless of footwear_required. The flag only
    # gates the ABSENCE case below, matching footwear_required's existing
    # role. ranked_slots["outerwear"] is already sorted by rank_key (item
    # alone) at line 119, so [0] is deterministic; it carries the same
    # known non-determinism as footwear/accessory selection across bases
    # (Engine v2's job -- see module docstring), not a new gap.
    items.append(outerwear_options[0])
elif rules.outerwear_required:
    gap_flags.append("missing_outerwear")
```

Attachment is **unconditional-when-available**, not gated on `outerwear_required` — mirroring exactly how footwear already behaves (`footwear_required` only controls the gap flag on absence, never whether attachment is attempted). This is the only design that makes Bug 2's fix actually reachable today: since no kind sets `outerwear_required=True`, gating attachment on it too would leave the bug "fixed" only in principle, never in practice. The AC's "surfaces candidates that include an outerwear item when the wardrobe has one" is satisfied literally and universally; the AC's "an explicit gap flag ... rather than a silent omission" is satisfied for the (currently override-only, see Open Questions) case where an occasion does mark `outerwear_required: true`.

**`_category_completeness_score` extension** — append after the existing footwear `if rules.footwear_required: ... else: ...` block, before `return sum(components) / len(components)`:

```python
    if rules.outerwear_required:
        outerwear_present = any(
            item.category is not None and CATEGORY_SLOT[item.category] == "outerwear"
            for item in items
        )
        components.append(1.0 if outerwear_present else 0.2)
```

Only adds a component when `outerwear_required` is truthy — for every currently-seeded occasion (all default to `None`/falsy) this function's output is byte-identical to before, so no existing `score_candidate`/`total_score` assertion changes. This keeps the gap flag and the score consistent with each other for the one code path (an explicit override) that can currently set the flag.

### Bug 3 — dupatta attachability + multiple accessories

Confirmed: `styling_rules_defaults.py:47` maps `"ethnic_dupatta": "accessory"`; `engine.py:149` gates accessory attachment on `preferred_accessory` being non-empty; `:150-152` filters to items whose category is in that set; only `ceremony`/`festival`/`religious` set `preferred_accessory_categories`, all `["accessory_jewellery"]` (current lines **122, 129, 136** — ticket cites 123/130/135, off by one, see note above).

**Data change** in `styling_rules_defaults.py` — for the `ceremony`, `festival`, and `religious` kind entries only, change:

```python
preferred_accessory_categories=["accessory_jewellery"],
```

to:

```python
preferred_accessory_categories=["accessory_jewellery", "ethnic_dupatta"],
```

Leave the other 6 kinds (`everyday`, `travel`, `social`, `milestone`, `professional`, `sport`) untouched — none currently set `preferred_accessory_categories` at all, so the guard at `engine.py:149` (`if preferred_accessory:`) keeps them accessory-free exactly as today. `"ethnic"` in the AC's "attachable for ethnic/ceremony/festival/religious occasions" reads as describing this existing ceremony/festival/religious group (already the ethnic-styled kinds, per their shared `preferred_footwear_categories=["footwear_ethnic", "footwear_formal"]`), not a fourth, nonexistent `OccasionKind` literal — `OccasionKind` has no `"ethnic"` member (`styling_rules_types.py:46-56`); do not invent one.

**Engine change** — replace the single-best-accessory block (lines 149-157) with a per-category loop so a candidate can carry one item from *each* matched preferred category, not just the single highest-ranked accessory overall:

```python
if preferred_accessory:
    for category in sorted(preferred_accessory):
        # One best item per preferred category, not one overall -- lets a
        # ceremony/festival/religious candidate carry a dupatta AND
        # jewellery simultaneously (raw ticket AC). sorted() over the set
        # gives deterministic category iteration order; the accessory_key
        # tiebreak within each category (score desc, id asc) is already
        # deterministic.
        category_options = [
            i for i in ranked_slots["accessory"] if i.category == category
        ]
        if category_options:
            best_in_category = sorted(
                category_options, key=lambda i: (-accessory_key(i), i.id)
            )[0]
            items.append(best_in_category)
```

If the wardrobe has a dupatta but no jewellery item, only the dupatta attaches — the loop naturally never forces a category that has no matching item, satisfying the raw ticket's "do not force jewellery" edge case with no extra logic.

### Module docstring update (AC #6)

Add a new paragraph to `styling_rules_engine.py`'s module docstring (after the existing "Colour harmony ... v1 heuristics" paragraph) naming every deliberately-unfixed gap so a future reader doesn't re-derive them as new findings:

- Footwear/accessory (and now outerwear) selection is a function of the item alone, never of the base — the same shoe/jacket/accessory can appear on every candidate. Fixed by Engine v2 stage ② (wide search) + stage ④ (MMR portfolio diversity).
- Colour is absent from the per-slot capping formula (`MAX_ITEMS_PER_SLOT` capping happens before `_colour_harmony_score` is ever called). Fixed by Engine v2 stage ②.
- `_colour_harmony_score` is star-topology (everything compared to `colored[0]`, order-dependent). Fixed by Engine v2 stage ③.
- `_hue_distance_score`'s flat `0.75` fallback for a named/unparsable colour degrades general colour-harmony scoring for such items at *any* occasion (distinct from the `wedding_guest` hard-exclusion guard, which SS-037 does fix) — needs the same hex→colour-family binning work as `BL-064`/`BL-079`'s open colour half, deliberately not built here.
- The near-white HSV threshold (`value >= 0.92, saturation <= 0.12`) is untouched — cream/ivory/gold-cream banarasi may be over-excluded at `wedding_guest`; a cultural/product decision, not a threshold-tuning exercise (`BL-111`).
- No occasion kind currently sets the new `outerwear_required` flag, so the "missing_outerwear" gap-flag path is real code but currently reachable only via an explicit `styling_rules` override, never a live default (see Open Questions).

## Edge cases

Carried forward verbatim from the raw ticket (all still apply, unchanged by this design):

- Wardrobe where every item has a named colour → engine must still return candidates for non-`wedding_guest` occasions (fail-closed is scoped to occasions with an active hard colour exclusion, never global).
- Cream/ivory/beige at `wedding_guest` — open product question, deliberately not decided here (`BL-111`).
- An occasion expecting a layer in a wardrobe with no outerwear → gap flag, not a dropped candidate.
- Multiple accessories on one candidate must not break the candidate-count bound or the prompt-payload size budget (~800 tokens for 5 candidates).
- A dupatta as the only accessory vs. dupatta + jewellery — both valid; do not force jewellery.

New, found while designing this pass:

- Outerwear now attaches **opportunistically to every occasion** that has an outerwear item available, not only ones that "expect a layer" — this is what actually makes Bug 2 reachable in practice today (see design rationale above). Consequence: a candidate could pair a western jacket over an ethnic saree base if that's what ranks best in the wardrobe. That's a *ranking/appropriateness* concern (does this pairing make sense), not an *expressibility* one (can this pairing exist at all) — explicitly Engine v2's job per this ticket's own scope boundary, not a new bug to fix here.
- The hard-exclusion fail-closed fix only inspects `color_primary`, never `color_secondary` — unchanged pre-existing behavior, not widened by this ticket (widening it would be scope creep beyond the AC's own `color_primary: "white"` example).
- Fail-closed's blast radius is wider than just `wedding_guest`/white: it applies to *any* occasion with a non-empty `effective_excluded` set (today only `wedding_guest → {"white"}`, but a future occasion adding e.g. `excluded_color_families: ["black"]` via its own `styling_rules` override would also now exclude every unparsable-colour item, not just literally-`"black"`-tagged ones). Correct per "the occasion has a hard colour exclusion" (the AC's own wording, not "excludes white specifically") — flagging for QA's awareness since it's the widest-reaching part of the fix.
- The `test_render_candidate_for_prompt_is_json_serializable_and_compact` budget (<600 chars, a proxy for the ticket's own ~800-token/5-candidate estimate) was sized against a max ~3-item candidate (base up to 2 + footwear 1, or +1 accessory for ceremony/festival/religious). After this fix a `ceremony`/`festival`/`religious` candidate can carry up to base(2) + footwear(1) + outerwear(1) + jewellery(1) + dupatta(1) = 6 items. This must be **re-measured, not assumed** — see Test plan.

## Test plan

All in `backend/tests/`, existing files, no new files.

**`test_styling_rules_engine.py`** (Bug 1):
- `test_wedding_guest_excludes_named_colour_string_literal_white` — item with `color_primary="white"` at `wedding_guest` → `generate_candidates` returns zero candidates (the AC's literal example).
- `test_wedding_guest_excludes_unparsable_colour_string` — item with `color_primary="not-a-colour"` at `wedding_guest` → zero candidates (fail-closed is not special-cased to the literal word "white").
- `test_non_wedding_occasion_allows_named_colour_string` — same `"white"`-tagged item at a non-`wedding_guest` occasion (e.g. `office`) → item IS still eligible (proves fail-closed is scoped, not global — covers the first carried-forward edge case).
- `test_item_is_hard_excluded_white_unit` — direct unit coverage of `_item_is_hard_excluded_white`: `"#FFFFFF"` → `True`; `"#8B0000"` → `False`; `"white"` → `True`; `None` → `False`.

(Bug 2):
- `test_outerwear_attached_when_available` — wardrobe with a valid base + footwear + one `western_outerwear` item → the resulting candidate's `item_ids` includes the outerwear item.
- `test_outerwear_required_gap_flag_when_missing` — occasion with `styling_rules={"outerwear_required": True}`, wardrobe has no outerwear item → candidate `gap_flags` contains `"missing_outerwear"`.
- `test_outerwear_not_required_no_gap_flag_when_missing` — default kind (no override), wardrobe has no outerwear item → no `"missing_outerwear"` flag (proves the fix doesn't overreach into flagging every occasion).
- `test_category_completeness_reflects_missing_required_outerwear` — `score_candidate` with `outerwear_required=True`: a candidate missing outerwear scores a lower `category_completeness` component than an otherwise-identical candidate that includes it.

(Bug 3):
- `test_ethnic_dupatta_attaches_for_ceremony_occasion` — wardrobe with a base + `ethnic_dupatta` item at a `ceremony`-kind occasion → candidate `item_ids` includes the dupatta.
- `test_candidate_can_carry_dupatta_and_jewellery_simultaneously` — wardrobe with both an `ethnic_dupatta` and an `accessory_jewellery` item at `festival` → candidate includes **both** ids at once.
- `test_dupatta_only_does_not_force_jewellery` — wardrobe has a dupatta but no jewellery item at `religious` → candidate includes the dupatta and is not penalized/dropped for lacking jewellery.
- `test_dupatta_not_attached_for_non_ethnic_kind` — same dupatta item at an `everyday`/`sport`-kind occasion → dupatta never attaches (regression guard: the 6 untouched kinds stay accessory-free).

(Regression/re-verification, no new assertions but must be explicitly re-run and reported, not assumed):
- `test_wedding_guest_excludes_all_white_hero_candidates`, `test_non_wedding_occasion_allows_white`, `test_other_ceremony_occasion_key_still_allows_white` — all hex-based, must pass unchanged (Bug 1's fix only changes behavior for *unparsable* colours).
- `test_render_candidate_for_prompt_is_json_serializable_and_compact` — re-measure the actual serialized length against the new max candidate size (up to 6 items for ceremony/festival/religious). If the `<600` char assertion now fails, this is a legitimate, ticket-caused change requiring an explicit renegotiated threshold with the real measured number recorded in the diff/worklog — same pattern as `BL-058`/`BL-067`, not a silent bump.
- `test_property_candidate_count_never_exceeds_max_candidates`, `test_property_deterministic_across_repeated_runs`, `test_deterministic_same_input_same_output`, `test_as_of_is_never_read_from_system_clock` — must still pass unmodified (AC explicitly requires the candidate-count bound and determinism properties hold).

**`test_styling_rules_defaults.py`** (Bug 3 data):
- `test_ceremony_festival_religious_preferred_accessories_include_ethnic_dupatta` — for each of the three kinds, `DEFAULT_STYLING_RULES_BY_KIND[kind].preferred_accessory_categories` contains both `"accessory_jewellery"` and `"ethnic_dupatta"`.
- `test_other_kinds_preferred_accessories_unchanged` — the other 6 kinds' `preferred_accessory_categories` remain `None` (regression guard).

**`test_styling_rules_properties.py`** (Bug 1, property coverage):
- Extend `_white_item_strategy` (or add a sibling strategy) to also generate the literal string `"white"` alongside the existing hex near-white forms, and confirm `test_property_wedding_guest_white_rule_holds_across_random_colors` (or a new sibling property test) holds across the mixed hex/named input space — this is the property-test equivalent of the AC's literal example, satisfying "Property-tested" per the raw SS-027 ticket's own wording that this ticket inherits.

## Open questions / blockers

- **No occasion kind sets `outerwear_required=True` anywhere.** The gap-flag half of Bug 2's AC is real, tested code but currently reachable only through a hand-constructed `styling_rules` override in a test, never through a live default or any of the 12 seeded `occasions` rows. Deciding which kinds should set it is a product/stylist content-authoring decision this ticket deliberately does not make (same posture as `BL-097`). Not a blocker for this ticket (the AC only requires the mechanism exist and be correct), but the Developer/QA should not expect to observe the gap flag against any currently-seeded occasion without constructing an override in the test itself.
- **`test_render_candidate_for_prompt_is_json_serializable_and_compact`'s `<600` char budget is unverified against the new max candidate size** (up to 6 items after this fix, vs. ~3-4 before). This needs an actual run, not an assumption — flagged above in both Edge cases and Test plan; if it fails, renegotiate with the real measured number, don't silently loosen it.
- **`BL-111`** (cream/ivory/beige possibly over-excluded at `wedding_guest`) is explicitly out of scope here per the raw ticket's own edge case, and stays open — re-scanned, not resolved (see Backlog logging).
- **`BL-064`/`BL-079`'s colour half** (no hex→colour-family vocabulary) is the real long-term fix for `_hue_distance_score`'s named-colour degradation this design leaves alone — re-scanned, not resolved.
- This ticket's own "Depends on: SS-027" is satisfied (SS-027 is shipped, PR #31 merged) — no external blocker.

## Backlog logging

Reviewed `docs/BACKLOG.md`'s Active table (grepped/read in full, tags `ai`/`schema`/`test` relevant to this ticket). Per the file's own ID-reservation banner (tops out at `BL-122`, warns `SS-036`'s Architect may be running in parallel from the same baseline), the IDs below are proposed starting at **`BL-128`** and **must be reconciled by hand** against whatever `SS-036`'s Architect pass claims, same precedent as the earlier `BL-097`–`BL-106` collision. I cannot edit `docs/BACKLOG.md` from this worktree — reporting these for the orchestrator to apply to the main checkout.

No existing Active row is resolved by this ticket (both directly-relevant rows — `BL-111` cream/ivory threshold, `BL-064`/`BL-079` colour vocabulary — are explicitly *not* touched here, by design). Proposing three new Active rows and two re-scan notes on existing rows:

**New rows (reconcile ID against SS-036):**

| ID | Title | Tag | Source | Description | Logged |
|----|-------|-----|--------|--------------|--------|
| BL-128 | `_hue_distance_score`'s flat `0.75` fallback for named/unparsable colours degrades general colour-harmony scoring at every occasion, not just `wedding_guest` | ai | SS-037 / Architect | SS-037 fixes the `wedding_guest` hard-exclusion guard (`_item_is_hard_excluded_white`) to fail closed on an unparsable colour, but deliberately leaves `_hue_distance_score`'s neutral `0.75` fallback unchanged for the *general* colour-harmony scoring path — it fires for any item pair at any occasion, not just where a hard exclusion is active, and fixing it properly needs the hex→colour-family binning decision `BL-064`/`BL-079` already track as open. Distinct gap from the guard, same root cause (named colours coexist with hex in `color_primary` per `001_initial.sql:52`). | 2026-08-05 |
| BL-129 | No occasion kind sets SS-037's new `outerwear_required` flag; opportunistic outerwear attachment can produce stylistically incongruous pairings | ai | SS-037 / Architect | Two related notes from SS-037's design: (1) the "missing_outerwear" gap-flag path is real, tested code but unreachable via any of the 12 seeded `occasions` rows until a future content-authoring pass decides which kinds expect a layer (folds into `BL-097`'s "real per-occasion content unauthored"); (2) outerwear now attaches to *any* occasion whenever the wardrobe has one (mirroring footwear's existing always-attach pattern), which can pair e.g. a western jacket over an ethnic saree base — a ranking/appropriateness concern, explicitly Engine v2's job per SS-037's own scope boundary, not a new expressibility bug. | 2026-08-05 |
| BL-130 | Prompt-payload size budget test needs re-verification after SS-037's outerwear + multi-accessory attachment | test | SS-037 / Architect | `test_render_candidate_for_prompt_is_json_serializable_and_compact`'s `<600` char assertion (a proxy for the raw ticket's own ~800-token/5-candidate estimate) was sized against a ~3-4 item max candidate. After SS-037, a `ceremony`/`festival`/`religious` candidate can carry up to 6 items (base 2 + footwear 1 + outerwear 1 + jewellery 1 + dupatta 1). SS-037's own Developer phase must actually re-run this test and report the real measured length; if it now fails, renegotiate the threshold explicitly (same pattern as `BL-058`/`BL-067`) rather than silently loosening it. | 2026-08-05 |

**Re-scan notes (append to existing rows, no ID change, still Active):**

- **`BL-111`** (cream/ivory/beige over-exclusion at `wedding_guest`): *"Re-scanned by SS-037 / Architect (2026-08-05): honored as directed — SS-037 fixes only the named-colour fail-closed guard, does not touch `NEAR_WHITE_VALUE_THRESHOLD`/`NEAR_WHITE_SATURATION_THRESHOLD`. Still needs the user's call."*
- **`BL-064`** (pattern/fabric/colour no controlled vocabulary): *"Re-scanned by SS-037 / Architect (2026-08-05): acknowledged, not resolved — SS-037's fail-closed fix is orthogonal to a colour-family vocabulary (it excludes any unparsable value without needing to classify it), so it closes the `wedding_guest` guard hole without requiring or building the vocabulary this row still tracks. See sibling `BL-128` for the specific scoring-degradation consequence this leaves open."*

## Risk classification

`Risk: low` — pure in-memory Python changes to an already-shipped, not-yet-wired module (no DB migration, no network call, no auth/payment surface, no schema change beyond an additive optional Pydantic field with no DB column behind it). The only consumer is SS-020, which doesn't exist yet, so nothing here is reachable by real traffic. Matches the raw ticket's own `Risk: low` and the CLAUDE.md fast-lane criteria exactly — no reclassification needed.
