# How Competitors Suggest Outfits Without Burning AI On Every Request

> **The question:** "How are these apps suggesting outfits from the existing wardrobe outright, and still saving costs without leveraging AI upfront?"
>
> **The short answer:** *almost none of what looks like AI is AI.* The suggestion surfaces are **SQL queries and combinatorics with editorial names**, rendered through a **client-side compositing engine**. AI appears in exactly three places, all of them either one-time-per-item, one-time-per-user, or explicitly paid.

---

## 1. The three-layer cost architecture (what Fits actually does)

```
┌─ LAYER 3 — GENERATIVE (paid, per-use, explicit) ─────────────────────────┐
│  AI Try-On · Enhance Image · AI photo-shoot backgrounds · palette render │
│  Cost: real. Metered in "AI credits". Never triggered without a tap.     │
│  Observed: "Costs 1 AI credit" shown at the point of action every time.  │
├─ LAYER 2 — ONE-SHOT INFERENCE (paid once, cached forever) ───────────────┤
│  Auto-tagging on upload · background removal · facial/colour analysis    │
│  · style-profile radar · the ~120-word "colour theory" paragraph         │
│  · the one-line caption on each generated outfit                         │
│  Cost: O(items) or O(1) per user. Amortised to ~zero over the lifetime.  │
├─ LAYER 1 — DETERMINISTIC (free, unlimited, runs constantly) ─────────────┤
│  Pairs you've never tried · Not yet worn · Ideas for your newest pieces  │
│  · Easy Summer Tailoring · daily suggestion carousel · shuffle 🔀        │
│  · Dressing Room compositing · every filter, sort, group and insight     │
│  Cost: zero marginal. THIS IS 95% OF WHAT THE USER EXPERIENCES AS "AI".  │
└──────────────────────────────────────────────────────────────────────────┘
```

**The whole trick is that Layer 1 carries the daily engagement and Layer 3 carries the revenue.** A user who opens Fits ten times a day and swipes through a hundred outfits costs them **nothing**.

---

## 2. Reverse-engineering each "AI" surface

Each of these is presented as intelligence. Each is a query. `[INFERENCE — high confidence, from observed behaviour in `03-FITS-TEARDOWN.md` §7]`

| Surface (their name) | What it actually is | Cost |
|---|---|---|
| **"Pairs you've never tried"** | `SELECT` valid (top, bottom, shoe) combos where `(top_id, bottom_id)` has **never co-occurred in a saved outfit**. Rank, take N. | 1 query |
| **"Not yet worn"** | `WHERE wear_count = 0` | 1 query |
| **"Ideas for your newest pieces"** | combos containing an item with `created_at > now() - 14d` | 1 query |
| **"Recently added items"** | `ORDER BY created_at DESC LIMIT 20` | 1 query |
| **"Easy Summer Tailoring"** (editorial rail) | a **named parameter preset** over the same generator: `season=summer, formality=smart-casual, palette=neutral` | 1 query |
| **Daily suggestion carousel** | generator + `weather` + `day_of_week`, run once per day per user | 1 query/day |
| **"Wardrobe usage 31%"** | `COUNT(DISTINCT item_id in any outfit) / COUNT(items)` | 1 query |
| **"Most/least versatile"** (Indyx) | `COUNT(DISTINCT outfit_id) GROUP BY item_id` | 1 query |
| **🔀 Shuffle** (whole outfit or per slot) | random pick per slot from the rules-filtered candidate pool | 0 — client-side |
| **Dressing Room render** | z-ordered transparent PNGs on a mannequin sprite with per-item saved `{x,y,scale,rotation,z}` | 0 — client-side |
| **Outfit Frames** | static template layouts + the already-composed outfit PNG | 0 — client-side |
| **Style-profile radar chart** | normalised weights from the onboarding style-tile picks | 0 — arithmetic |
| **Colour-harmony score** (Nouva's USP) | hue-distance arithmetic in HSL/Lab | 0 — arithmetic |

**The tell that confirms this:** Fits' "Pairs you've never tried" full page shows **30 tiles, of which 29 are paywalled**, and uncomputed tiles render a blurred placeholder reading *"Creating outfit…"*. They generate **a batch of 30 in one pass** and gate 29. If each outfit cost an LLM call, generating 30 for a free user who will see one would be economically insane. **They generate in bulk because generation is free.**

---

## 3. Where the AI genuinely is, and how they keep it cheap

| # | Real AI use | Frequency | Cost-control technique |
|---|---|---|---|
| 1 | **Auto-tagging on upload** (vision) | once per item | cached on the row forever; batched; user can edit instead of re-running |
| 2 | **Background removal** | once per item | cheap specialised model (not an LLM), non-blocking batch toast, `SD/HD` user choice (Indyx) |
| 3 | **Facial / colour analysis** | **once per user** | result stored as a named palette artefact and reused on every surface thereafter |
| 4 | **The prose "why"** (captions, colour-theory paragraph) | once per artefact | **cached against the outfit/palette id**, never regenerated on view |
| 5 | **Generative try-on / enhance** | on explicit tap | **credit-metered, priced at the point of use, blurred-preview upsell** |

**Note #4 specifically.** The caption *"Refined bohemian ease for a warm Thursday"* is the only part of "Pairs you've never tried" that could involve a language model — and it is generated **once, at batch time, for the outfit**, then stored. Scrolling the rail 50 times costs nothing.

> **This is exactly what our `suggestion_narration_cache` (migration `019`) is for.** We already built the right thing.

---

## 4. What we already have — and the honest gap

### 4.1 Already built (verified against the repo, 2026-08-13)

| Ours | File | Equivalent to |
|---|---|---|
| Deterministic 4-stage pipeline (eligibility → wide candidate search → attribute scoring → MMR portfolio) | `backend/services/engine_v2.py` + 6 stage modules | Layer 1, and **more principled than theirs** |
| **`generate_portfolio` never calls an AI provider** — it is pure Python, the only I/O is reference-data + wear/impression history | `engine_v2.py` docstring, "Cost-accounting posture" | the core cost win |
| Novelty scoring from wear + impression history | `engine_v2_novelty.py` | "Pairs you've never tried", "Not yet worn" |
| Pairwise colour harmony | `engine_v2_colour.py` | Nouva's entire USP |
| MMR portfolio diversification | `engine_v2_portfolio.py` | Fits' recommendation-breadth slider |
| Effort dial **E0/E1/E2**, `app_config`-driven, degrades on provider outage or budget ceiling | `engine_v2_effort_dial.py` | **nobody else has this** |
| Budget gate + cost ledger | `cost_budget_gate.py`, `supabase_cost_ledger.py` | the credit model's prerequisite |
| Narration cache | migration `019_suggestion_narration_cache.sql` | cached captions (#4 above) |
| Impression/outcome logging | `suggestion_log_service.py`, migration `013` | the compounding-data moat |

**Verdict: our Layer 1 is *better engineered* than Fits'.** We have MMR diversification, occasion-aware novelty, and a cost-tier dial they don't.

### 4.2 The actual gap — three items, none of them the engine

1. **We compute portfolios on request; they precompute batches.**
   Fits' rails exist *before the user asks*. Our engine runs when the user opens the suggestion flow. **Fix:** a nightly/on-write job that materialises the standard rails per user.
2. **We have no rail surfaces at all.** The engine's output has exactly one consumer (the occasion flow, SS-023). The same engine, called with different presets, is six home-screen rails. **This is the highest-leverage, lowest-cost work in the entire competitive response** — new queries and new UI over an engine that already exists.
3. **We render item stacks, not outfits.** `OutfitItemStack.tsx` shows a list of garments. Fits renders a *composed image*. Without on-body/collage rendering, precomputed rails have nothing beautiful to show.

### 4.3 One live blocker to be honest about
`engine_v2.py`'s own docstring records that **`volume_balance` / `register_coherence` are "100% LIVE-INERT today"** — no live `wardrobe_items.category` value resolves through `garment_types`, because SS-034 seeded the new vocabulary under different keys than the 21-value enum still in use (`BL-132`). **The taxonomy migration is therefore not just an India feature — it is what switches on scoring terms we've already built and paid for.** That raises its priority in `07-EPICS-AND-TICKETS.md`.

---

## 5. The recommended architecture for StyleSense

### 5.1 Rail presets — one generator, six surfaces
Every home rail is `EngineV2.generate_portfolio` with a different preset. No new engine work.

| Rail | Preset over the existing pipeline |
|---|---|
| **Today's picks** | `occasion = user's most-frequent for this weekday`, weather-filtered, `n=5` |
| **Pairs you've never tried** | novelty stage weighted to max; hard filter on pairs with no prior co-occurrence |
| **Not yet worn** | eligibility restricted to `wear_count = 0` anchors |
| **Ideas for your newest pieces** | eligibility restricted to `created_at > now() - 14d` anchors |
| **Festive picks** (India-only) | `occasion_kind = festive`, seeded from the occasion registry |
| **Beat the heat / monsoon-ready** | fabric + coverage filters from the SS-036 registry |

### 5.2 Precompute schedule
| Trigger | What runs | Why |
|---|---|---|
| Nightly (per active user, IST early morning) | all rails, `n≈20` each, persisted | rails are instant at 8am, the moment that matters |
| On wardrobe write (debounced ~10 min) | affected rails only | new item → "Ideas for your newest pieces" is fresh |
| On wear log | novelty-dependent rails | keeps "never tried" honest |
| On demand (occasion flow) | live call | the user asked; latency budget is theirs |

Store in a `suggestion_rails` table keyed `(user_id, rail_key, computed_at)`, holding item-id tuples + score + optional cached narration. **Serving a rail becomes one indexed read.**

### 5.3 Narration policy (the only place cost can leak)
- **E0:** template strings only — `"{occasion} look in {palette}"`. Zero cost. Ship this first.
- **E1:** **one** LLM call per *batch* of 20 outfits, returning 20 captions; cached in `suggestion_narration_cache`. ≈ ₹0.02/user/night `[INFERENCE — order-of-magnitude]`.
- **E2:** per-outfit narration with reasoning, only on the detail view, only on tap.
- **Never** narrate on scroll. Never regenerate a cached caption.

### 5.4 What to meter (the India price-point model)
| Tier | Included | Metered |
|---|---|---|
| Free | unlimited rails, unlimited Dressing Room, unlimited collage, unlimited shuffle, full filters/insights on ≤N items | 1 enhance/mo, 0 try-on |
| **₹149/mo** | everything above unlimited, full insights, planner | 20 enhance-credits/mo, 5 try-on |
| Credit packs | — | ₹49 / ₹149 / ₹399 |

**The rule: never meter anything that runs on Layer 1.** Metering deterministic output is what Nouva does (3 outfits/week), and it makes the product feel broken. Meter only what actually costs money.

---

## 6. The five principles, stated plainly

1. **Combinatorics + rules + a good name beats an LLM call**, and the user cannot tell the difference — *"Pairs you've never tried"* is a `NOT EXISTS` clause with a copywriter.
2. **AI is for turning a photo into data (once) and data into prose (once).** Never for choosing which of your own clothes go together — you already have the data to decide that deterministically.
3. **Precompute in batches, serve from a table.** Generation and viewing must be decoupled, or cost scales with engagement — the exact opposite of what you want.
4. **Cache every generated string against a stable key, forever.**
5. **Put the paid generative moment where the delight is** (see it on me, make it beautiful), price it visibly at the point of use, and never let it block a free path.

> **We built the hard half of this before we knew it was the differentiator.** Everything remaining is presets, a precompute job, and rendering.
