# Competitive Analysis Part 7 — Epics, Tickets & Sequencing

**Derived from:** `02-FEATURE-MATRIX.md` (what's missing) · `06-UIUX-SPEC.md` (how it looks) · `08-CHEAP-SUGGESTION-ENGINE.md` (how it stays cheap).
**Ticket IDs:** `SS-040` onward. **`SS-030`, `SS-031`, `SS-032` are already reserved** by `docs/proposals/EXECUTION-PLAN.md` (Occasion Calendar, Multi-Day Event Series, Global Trend Clusters) — do not reuse.
**Process:** each ticket below is a *draft spec*. Promote one to `docs/tickets/raw/SS-0XX.md` and run `/ticket SS-0XX` through the normal architect→developer→qa→devops pipeline. `Risk:` is set here so the lane (fast vs. full) is decided up front per `CLAUDE.md`.

---

## The sequencing principle

We are behind on **commodity** and ahead on **compounding** (`02-FEATURE-MATRIX.md` §M). So:

> **Buy back parity with the cheapest possible work, in the order that unblocks the most downstream value — and spend the saved time on the India moat, which nobody can copy.**

Three ordering rules that fall out of the analysis:
1. **Data model before surfaces.** Analytics, filters, insights and resale all read the *same* extra columns. Ship the schema once (E1) and six features become cheap.
2. **Taxonomy is not a "later, India thing" — it is a live bug.** `engine_v2.py`'s docstring records that `volume_balance` and `register_coherence` are **"100% LIVE-INERT today"** because no live `wardrobe_items.category` resolves through `garment_types` (`BL-132`). **Scoring terms we already built and paid for are switched off until the taxonomy migration lands.** That moves E2 from "differentiator" to "critical path".
3. **Rails before builder.** The engine already produces portfolios; six home rails are presets + a precompute job + a list UI. The Dressing Room is 4–6 weeks and an art budget. Rails first — they make the app feel alive in one sprint.

---

## EPIC A — Wardrobe Depth *(the data model everything else reads)*

**Why:** `02-FEATURE-MATRIX.md` §B scores us **8/30** vs Indyx 28/30. Analytics (Epic D), filters (A3), resale, and the shopping hook all block on these columns. **Highest downstream leverage in the whole plan.**

### SS-040 — Rich Item Attributes & Lifecycle Schema
`[Infra]` `[P0]` `[5 pts]` · **`Risk: high`** (schema + migration + RLS)
Add to `wardrobe_items`: `brand`, `size`, `mrp_price`, `purchase_location`, `source` (`purchase|gift|self_made|inherited|tailored`), `is_secondhand`, `condition`, `condition_details`, `origin_country`, `resale_value`, `date_sold_donated`, `sold_price`, `personal_note`, `description`, `shopping_url`, `seasons[]` (`summer|monsoon|winter|festive`), `is_favourite`, `is_archived`, `do_not_style`, `is_private`, `location_id`, `custom_tags[]`, `render_transform` (JSONB, for E5), `images[]` (multi-image).
New tables: `wardrobe_locations`, `brands` (seeded with Indian retail: Myntra house brands, Westside, Max, Snitch, Souledstore, Spykar, FabIndia, W, Biba, Manyavar, Allen Solly, Peter England, Zudio…).
**AC:** all columns nullable + RLS-covered; `cost_per_wear` unaffected; regenerated `types/supabase.ts`; **`do_not_style` items are excluded by `engine_v2_eligibility`** (wire it, don't just add the column); GIN index on `custom_tags`.
> `do_not_style` is the single cheapest suggestion-quality feature in the category (`04-INDYX-TEARDOWN.md` §7.7). Ship it in the same migration that adds it.

### SS-041 — Item Detail Redesign (tabbed route)
`[Feature]` `[P0]` `[3 pts]` · `Risk: med` · depends SS-040
Per `06-UIUX-SPEC.md` §2.3: promote `ItemDetailSheet` to a route with `Cost/Wear | Details | Tags` tabs, multi-image strip, "appears in N outfits", status pills.

### SS-042 — Filter, Sort & Group Overhaul
`[Feature]` `[P0]` `[3 pts]` · `Risk: low` · depends SS-040
Per `06-UIUX-SPEC.md` §2.2. Includes **Usage** (`not used in outfits`), **CPW sort**, **Group by**, active-filter count badge, and **Occasion** as a filter dimension (our edge, placed high in the sheet).

### SS-043 — Chrome-less Wardrobe Grid + Multi-select
`[Feature]` `[P1]` `[2 pts]` · `Risk: low`
Per `06-UIUX-SPEC.md` §2.1. Remove card chrome, variable heights, `FlashList`, long-press multi-select with bulk archive / favourite / do-not-style / add-to-collection.

---

## EPIC B — India Taxonomy & Outfit Grammar *(the moat, and a live-inert bug fix)*

**Why:** the only genuinely uncopyable position we have (`01-…` §6, `02-…` §L) — **and** the fix for `BL-132`.

### SS-044 — Indian Garment Types & Category Migration
`[Infra]` `[P0]` `[5 pts]` · **`Risk: high`** · resolves `BL-132`
Migrate live `wardrobe_items.category` (21-value enum, still in use) onto the `garment_types` registry keys seeded by SS-034, **and** extend the registry with the Indian vocabulary: kurta, kurti, anarkali, sherwani, Nehru jacket, bandhgala, choli/saree-blouse, saree, lehenga, salwar, churidar, palazzo, patiala, sharara, garara, dhoti, lungi, dupatta, stole, jutti, kolhapuri, mojari, chappal, bangles, jhumka, maang-tikka, mangalsutra, payal, pagdi/safa.
Each gets `coverage`, `formality`, `layer_depth`, `volume`, `register` populated — **the attributes `engine_v2_attribute_scoring` already reads but currently gets nothing for.**
**AC:** every live wardrobe row resolves to a `garment_type`; `volume_balance` and `register_coherence` produce non-neutral scores on a real wardrobe (**verify against live data, not fixtures** — this is the whole point of the ticket); backfill is reversible.

### SS-045 — Garment Sets & Composition Grammar
`[Feature]` `[P0]` `[5 pts]` · **`Risk: high`** · depends SS-044 · relates `BL-116`
Model outfits whose components are inseparable or co-required:
- **`set` type:** saree = `saree_drape + blouse + petticoat`; kurta-set = `kurta + bottom + dupatta`; lehenga = `lehenga + choli + dupatta`.
- **Co-requirement rules:** suggesting a saree *must* pull a blouse; a churidar is not a standalone bottom for a Western top.
- **Exclusion rules:** never propose a kurta with formal trousers unless `indo_western` is in the user's archetypes.
- **`drape_style`** on saree/dupatta items.
**AC:** engine never emits an incomplete ethnic outfit; a saree set consumes its components from the candidate pool; rules are data-driven (`app_config` / registry), not hardcoded.
> **This is the deepest moat in the plan.** Fits and Indyx cannot represent a saree at all; retrofitting sets would require redesigning their outfit model.

### SS-046 — Indian Seasons, Occasions & Culture Rules
`[Feature]` `[P1]` `[3 pts]` · `Risk: med` · depends SS-044
Replace Spring/Summer/Fall/Winter with **Summer / Monsoon / Winter / Festive**. Extend the occasion registry: mehendi, haldi, sangeet, reception, engagement, puja, Diwali, Karva Chauth, Navratri, temple visit, office-festive, family function.
Encode culture rules as data: *never white for `wedding_guest`*, *no leather for temple*, *monsoon → synthetic/quick-dry over silk*, *festive → silk/brocade/zari over denim*.

### SS-047 — Icon & Asset Library (India-inclusive)
`[Task]` `[P1]` `[3 pts]` · `Risk: low`
Per `06-UIUX-SPEC.md` §1.7: ~85 garment line icons (incl. 15 Indian), ~40 fabric texture swatches (khadi, chanderi, banarasi, chikankari, ikat, bandhani, block print, brocade…), ~30 colours + 8 patterns (incl. paisley, bandhani, ikat), ~24 body sprites at South Asian proportions, ~18 hairstyles × 10 colours (incl. braid, oiled centre-part, bun-with-gajra, pagdi, hijab).
**AC:** every `garment_type` has an icon; icons serve as image fallbacks; assets ship as an optimised sprite/atlas.

---

## EPIC C — Suggestion Surfaces *(highest ratio of perceived value to cost)*

**Why:** the engine already exists (`engine_v2.py`) and has exactly one consumer. Per `08-CHEAP-SUGGESTION-ENGINE.md` §4.2 this is presets + a job + UI, at **zero marginal AI cost**.

### SS-048 — Rail Presets & Precompute Job
`[Infra]` `[P0]` `[4 pts]` · `Risk: med`
New `suggestion_rails` table `(user_id, rail_key, computed_at, payload jsonb)`. Presets over `EngineV2.generate_portfolio`: `todays_picks`, `never_tried_pairs`, `not_yet_worn`, `newest_pieces`, `festive_picks`, `weather_tailored`.
Triggers per `08-…` §5.2 (nightly IST, on wardrobe write debounced, on wear log, on demand).
**AC:** serving a rail is **one indexed read**; nightly job is idempotent and resumable; **zero AI provider calls in the E0 path** (assert it in a test, matching `engine_v2.py`'s existing cost-accounting posture); narration via `suggestion_narration_cache` at E1, templates at E0.

### SS-049 — Home Screen Rewrite
`[Feature]` `[P0]` `[4 pts]` · `Risk: low` · depends SS-048
Per `06-UIUX-SPEC.md` §2.5. Weather+day suggestion carousel, Stylist tiles, six rails, 3-slot floating tab bar. Every header `›` → full page with blur-tease paywall (§3.6).

### SS-050 — Stylist Hub: four jobs + structured request form
`[Feature]` `[P1]` `[4 pts]` · `Risk: med`
Per `06-UIUX-SPEC.md` §2.10. Tiles: **Rate my fit · Find my colours · Pack for a trip · Find gaps**. The suggestion request schema extends to `{occasion, when, seed_items[], vibe[], company, free_text}` (`03-FITS-TEARDOWN.md` §7.16) — **`seed_items` ("style around this kurta") is the single most-requested styling job and costs only a pre-filter.**
**AC:** the form is the primary path; the prompt is mostly enum values; free text is optional and last.

### SS-051 — Recommendation Breadth Control
`[Feature]` `[P2]` `[2 pts]` · `Risk: low`
Expose MMR λ (SS-038) as the Fits-style slider with a **live halo visualisation** (`03-…` §1.11) — Focused / Balanced / Broad, stored as a 0–8 value. Turns an engine hyperparameter into a user-legible setting and pre-empts both "too boring" and "not me".

---

## EPIC D — Analytics & Insights

**Why:** we score **1.5/20** vs Indyx 20/20 (`02-…` §G). All of it is SQL over data SS-040 adds.

### SS-052 — Wardrobe Insights (Composition / Usage / Value)
`[Feature]` `[P1]` `[5 pts]` · `Risk: low` · depends SS-040
Per `06-UIUX-SPEC.md` §2.8. **Load the `dataviz` skill before writing any chart code.**
Must include **versatility** (`COUNT(DISTINCT outfit_id) GROUP BY item_id`) — Indyx's best metric, trivial to compute, and simultaneously a ranking signal for the engine.
**AC:** every metric card carries a `?` tooltip stating its formula *and exclusions* (`04-…` §10.3); `Undefined` is always a visible slice; ₹ in `en-IN`; free/paid split per `03-…` §6.3 (anxiety free, resolution paid).

### SS-053 — Wear Logging & Planner
`[Feature]` `[P1]` `[4 pts]` · `Risk: med`
Per `06-UIUX-SPEC.md` §2.7. Day/Month, week strip with dots, big paged outfit card, per-day note.
**AC:** assigning an outfit to a date ≤ today **logs the wear with `occasion_key` (SS-035) and updates CPW**, and the UI states it: *"Logged · cost per wear now ₹142"*.

---

## EPIC E — Outfit Studio *(the flagship experience)*

**Why:** we score **2/25** vs Fits 21/25 (`02-…` §D). This is what makes the app fun and it costs **nothing per use**.

### SS-054 — Collage Canvas
`[Feature]` `[P1]` `[4 pts]` · `Risk: low`
Free-canvas flat-lay: drag/scale/rotate/z-order/lock/delete, snapshot to PNG on save. Reanimated worklets; ≤12 layers.

### SS-055 — Dressing Room (on-body compositing)
`[Feature]` `[P0]` `[8 pts]` · `Risk: med` · depends SS-047, SS-040 (`render_transform`)
Per `06-UIUX-SPEC.md` §2.6. Mannequin + hairstyle; garments as z-ordered transparent PNGs; **per-item persisted `render_transform`** (the mechanic that makes it look right); tap-and-swipe slot swap; per-slot and whole-outfit shuffle; layers panel with depth presets and half/half live preview.
**Ethnic rendering:** saree drape sprite with blouse beneath; dupatta drape-style picker (front-pallu / shoulder / both / head).
**AC:** zero network calls to render; swap is <100ms; transforms persist across outfits and across body changes.
> **Verify the ethnic drape rendering with a real saree before calling this done** — it is the part with no prior art to copy, and the part that differentiates us.

### SS-056 — Body Type & Avatar
`[Feature]` `[P1]` `[3 pts]` · `Risk: low` · depends SS-047
(gender presentation × S/M/L/XL × regular/short-leg/long-leg) sprite matrix + hairstyle/hair-colour picker. **No ML, no measurements** — a finite indexed sprite library, exactly as Fits does it (`03-…` §5.8). Also yields a free body-shape signal for the engine.

### SS-057 — Save Outfit, Occasions, Visibility & Collections
`[Feature]` `[P1]` `[3 pts]` · `Risk: low`
Save sheet per `06-UIUX-SPEC.md` §2.6 step 4. Collections typed `wishlist | packing | capsule | inspiration | custom`; wishlist items **excluded from wardrobe stats** (`04-…` via `status`). Outfit gets `source` (`self|ai|expert|social`) and `status` (`owned|recommendation|wishlist`).
> **Add `source` and `status` now even though nothing uses them yet.** Two columns today; a schema migration on a large table plus unattributable history if we wait. This is the one Indyx schema decision that is painful to retrofit (`04-…` §7.6).

---

## EPIC F — Ingestion Acceleration *(the funnel fix)*

**Why:** every app dies at cataloguing (`01-…` §1). We score 6/17 vs Fits 15/17.

### SS-058 — Seed Wardrobe at Onboarding
`[Feature]` `[P0]` `[2 pts]` · `Risk: low`
Per `03-…` §1.12. A curated India starter set (white kurta, dark jeans, black formal trousers, white sneakers, plain white shirt, chappals, dupatta, black kurti…), gender-matched, pre-checked.
**AC:** a brand-new user leaves onboarding with ≥6 items and the engine can produce a real outfit on day 0.
> Cheapest cold-start fix available. 2 points to make the whole product work on first open.

### SS-059 — Catalogue Search Ingestion
`[Feature]` `[P1]` `[5 pts]` · `Risk: med`
Add an item by searching a product catalogue instead of photographing it. Seed from Indian retail; store packshot + brand + type. Popular searches seeded per `06-UIUX-SPEC.md` §2.4.

### SS-060 — Photo-Library Outfit Mining
`[Feature]` `[P2]` `[5 pts]` · **`Risk: high`** (privacy surface)
Per `03-…` §1.4/§1.18. Scan the camera roll **on-device** for outfit photos, quantify the find (*"we found N outfit photos → ~M items"*), import behind the paywall.
**AC:** classification is on-device; nothing uploads without explicit per-batch consent; the priming screen states this plainly (`06-UIUX-SPEC.md` §3.2). **Run the boundary sweep + a privacy review — this is the most sensitive feature in the plan.**

### SS-061 — Order-Email / WhatsApp Receipt Ingestion
`[Feature]` `[P2]` `[5 pts]` · **`Risk: high`**
Parse Myntra / AJIO / Flipkart / Nykaa Fashion / Meesho order confirmations → brand, name, price, purchase date, image, pre-populated for approval.
**AC:** parse failures degrade to manual entry; no credential access — forward-to-address or share-sheet only.
> This is the only ingestion path that reliably captures **price and purchase date**, i.e. the two inputs every Epic D metric depends on.

### SS-062 — Non-blocking Processing & Quality Coaching
`[Feature]` `[P1]` `[2 pts]` · `Risk: low`
Replace blocking `ProcessingStep` with the dismissible batch toast (`06-UIUX-SPEC.md` §3.4); add the photo-quality coaching sheet (§3.3).

### SS-063 — Image Enhancement (packshot generation)
`[Feature]` `[P2]` `[4 pts]` · `Risk: med`
Opt-in generative packshot with **before/after inset comparison** (`04-…` §7.3), priced per `06-UIUX-SPEC.md` §3.5. First real consumer of the credit model.

---

## EPIC G — Onboarding & Profile

### SS-064 — Onboarding Funnel Rewrite
`[Feature]` `[P0]` `[5 pts]` · `Risk: med`
Per `06-UIUX-SPEC.md` §2.9 — 14 one-question screens, "why we ask" on every ask, photo-based **Indian style archetypes**, breadth slider, CPW value-prop interstitial, progress theatre, radar-chart reveal, seed wardrobe.
**AC:** every existing SS-004/SS-007 preference still captured; resumable; skippable; **measure completion vs. the current 4-step wizard** — this is the ticket most likely to move activation.

### SS-065 — Colour Analysis & Palette Artefact
`[Feature]` `[P2]` `[4 pts]` · `Risk: med`
Per `03-…` §7.10/§7.13: form (selfie + body type + season + colour temperature with an **Automatic** escape hatch) → named palette card, branded and shareable, plus a **free** "N% of your wardrobe matches this palette" stat and a cached prose rationale.
**AC:** **calibrated and verified on Indian skin tones** — seasonal colour analysis is notoriously calibrated on light skin, and getting this wrong is a credibility failure, not a bug. `Automatic` must be genuinely automatic, with manual warm/cool override.

---

## EPIC H — Social & Growth

### SS-066 — Outfit Frames (branded social export)
`[Feature]` `[P1]` `[3 pts]` · `Risk: low`
Templates per `06-UIUX-SPEC.md` §2.11 incl. a **festive frame**; every export carries `@handle · StyleSense`; **WhatsApp first** in the share row.
> Highest-leverage growth feature: free, attributed, aesthetically desirable distribution.

### SS-067 — Public Web Closet
`[Feature]` `[P2]` `[4 pts]` · **`Risk: high`** (public data exposure)
Shareable web profile (Expo web) with closet privacy states (`closed | open | featured`) **and item-level private overrides** (`04-…` §4.3).
**AC:** RLS-verified — nothing private ever renders; boundary sweep required.

### SS-068 — OOTD & Follow Graph
`[Feature]` `[P2]` `[5 pts]` · `Risk: med`
24h fit-of-the-day story, follow graph, likes.

---

## EPIC I — Monetisation

### SS-069 — Credits, Plans & Paywalls
`[Feature]` `[P0]` `[5 pts]` · **`Risk: high`** (payments)
Per `08-…` §5.4: Free / ₹149-mo / annual, plus credit packs (₹49/₹149/₹399) on Razorpay. Blur-tease paywalls (§3.6); credit cost shown at the point of use (§3.5).
**AC:** **never meter a deterministic (Layer 1) surface** — rails, Dressing Room, collage, shuffle, filters stay unlimited on free. Razorpay webhook HMAC verified first, per `CLAUDE.md`. Reconciles against the SS-029 ledger.

---

## Sequencing

### Wave 1 — "the app feels alive" (4–6 weeks)
`SS-040` → `SS-044` → `SS-048` → `SS-049` → `SS-058` → `SS-062` → `SS-042`
*Rationale:* SS-040 unblocks everything; SS-044 turns on scoring terms we've already paid for (`BL-132`); SS-048+SS-049 convert the existing engine into six visible surfaces at zero AI cost; SS-058 fixes cold start for 2 points; SS-062+SS-042 remove the two worst UX papercuts.
**Outcome:** a user opens the app and immediately sees outfits made from their clothes. That is the whole gap between "basic" and "alive".

### Wave 2 — "the app is beautiful" (6–8 weeks)
`SS-047` → `SS-055` → `SS-056` → `SS-054` → `SS-057` → `SS-041` → `SS-043` → `SS-066`
*Rationale:* the Dressing Room is the flagship and needs the asset library first. SS-066 ships alongside so the beautiful thing is immediately shareable.

### Wave 3 — "the app is smart about India" (4–6 weeks)
`SS-045` → `SS-046` → `SS-052` → `SS-053` → `SS-050`
*Rationale:* garment sets are the deepest moat and need the taxonomy (Wave 1) plus the renderer (Wave 2) to be visible. Analytics and planner land here because they need accumulated wear data to be non-empty anyway.

### Wave 4 — "the app makes money and grows" (6–8 weeks)
`SS-069` → `SS-063` → `SS-059` → `SS-064` → `SS-065` → `SS-051` → `SS-060` → `SS-061` → `SS-067` → `SS-068`

### Parallelisation (per `CLAUDE.md`'s two-lane rule)
- **Full lane, serialised** (`Risk: high`): SS-040, SS-044, SS-045, SS-060, SS-061, SS-067, SS-069.
- **Fast lane, parallel worktrees** (`low`/`med`, no file overlap): {SS-042, SS-043, SS-062}, {SS-047, SS-054, SS-056}, {SS-052, SS-053}, {SS-051, SS-066}.

---

## What we are deliberately NOT building

| Not doing | Why |
|---|---|
| Human stylist marketplace (Indyx) | Two-sided supply is a company, not a feature. **Revisit at scale** — Indian labour economics make ₹999–₹2,999 sessions plausible ARPU, but not before we have demand. |
| Resale marketplace (Whering×eBay) | Needs liquidity we don't have. **Ship the *data* (`resale_value`, `condition`, `date_sold`) in SS-040 so the option stays open**, and partner later. |
| Multi-week style course (Indyx workshop) | Content business. |
| Conversational chat as the primary AI surface | `03-…` §7.15 shows even Fits collects the real request via a **form**. Chat is a skin; the form is the product. |
| Generative AI on the daily path | Structurally opposed to our cost position (`08-…`). Generative stays opt-in and paid, always. |
| Colour-harmony scoring as a headline USP (Nouva) | We already have `engine_v2_colour`. It's a feature, not a position. |

---

## Backlog rows to log

Append to `docs/BACKLOG.md` **Active** (IDs from `BL-151`) when the first of these tickets is promoted:
| Proposed | Title | Tag |
|---|---|---|
| BL-151 | Indian brand catalogue seed list — sourcing + licensing for SS-040/SS-059 | schema |
| BL-152 | Seasons enum change (Spring/Fall → Summer/Monsoon/Winter/Festive) breaks any existing season data | schema |
| BL-153 | `dataviz` skill palette must be reconciled with our marigold/peacock tokens before SS-052 | tokens |
| BL-154 | Dark-mode tokens absent app-wide (`06-UIUX-SPEC.md` §1.10) | tokens |
| BL-155 | Marigold `#E8A420` fails 4.5:1 as text on `surfacePrimary` — audit all uses | tokens |
| BL-156 | Camera-roll mining (SS-060) needs a privacy review + Play/App Store policy check before build | infra |
| BL-157 | Receipt parsers (SS-061) are per-retailer and will break silently — needs monitoring | infra |
| BL-158 | Saree/dupatta drape rendering has no prior art — prototype before committing SS-055's estimate | ai |
