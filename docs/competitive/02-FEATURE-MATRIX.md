# Competitive Analysis Part 2 — Exhaustive Feature Extraction & Classification

Legend: **✅** has it · **◐** partial/weak · **❌** absent · **💰** paid-gated · **—** not applicable
Class: **[C]** Commodity (table stakes) · **[D]** Differentiator (few have it) · **[U]** USP (one owns it) · **[M]** Moat-bearing (hard to copy or compounds)

Columns: **SS** = StyleSense today · **FI** = Fits · **IX** = Indyx · **WH** = Whering · **AC** = Acloset · **NV** = Nouva · **GW** = GetWardrobe · **SB** = Stylebook · **PU** = Pureple · **CL** = Clueless

> Fits/Indyx columns are from first-hand screenshot analysis (`03-`/`04-` teardowns). Other columns are from the vendor/comparison sources in `01-MARKET-AND-BUSINESS.md` §Sources and are therefore coarser `[VERIFIED 2026-08-13 at feature-presence granularity only]`.

---

## A. INGESTION — getting clothes into the app

| # | Feature | Class | SS | FI | IX | WH | AC | NV | GW | SB | PU | CL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 | Camera capture | [C] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| A2 | Photo-library import | [C] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| A3 | Bulk/multi-select upload | [C] | ✅ | ✅ | ✅ | ✅ | ✅ | ◐ | ✅ | ✅ | ◐ | ◐ |
| A4 | **Background removal** | [C] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ◐ | ❌ | ✅ |
| A5 | **AI auto-tagging** | [C] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ◐ | ❌ | ❌ | ✅ |
| A6 | **Product-catalogue search** ("add Nike AF1 without a photo") | **[D]** | ❌ | ✅ | ◐ | ✅ | ◐ | ❌ | ◐ | ❌ | ❌ | ❌ |
| A7 | **Camera-roll outfit mining** ("we found 65 outfit photos → 195 items") | **[U/M]** | ❌ | ✅💰 | ❌ | 🔜 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A8 | **Email-receipt extraction** | **[U/M]** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A9 | **Seed/starter wardrobe at onboarding** | **[D]** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A10 | **Extract garment from a worn-outfit photo** | **[D]** | ❌ | ✅ | ❌ | 🔜 | ◐ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A11 | URL / shop-link import | [D] | ❌ | ✅ | ✅ | ✅ | ◐ | ❌ | ✅ | ❌ | ❌ | ❌ |
| A12 | **Photo-quality coaching sheet** (😍 shop shot / 🙂 flat / 🙁 hanging) | [D] | ❌ | ✅ | ◐ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A13 | **Non-blocking batch processing toast** | [D] | ❌ | ✅ | ◐ | ◐ | ◐ | ◐ | ◐ | — | — | ◐ |
| A14 | **Image enhancement → packshot** | **[D]** | ❌ | ✅💰 | ✅💰 | 🔜 | ◐ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A15 | SD/HD resolution choice | [D] | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| A16 | Multiple images per item | [D] | ❌ | ✅ | ✅ | ◐ | ◐ | ❌ | ✅ | ✅ | ◐ | ❌ |
| A17 | Rotate / retake in-flow | [C] | ◐ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> **A6–A10 are the ingestion moat.** Together they are the difference between "photograph 60 garments" and "tap twice". `[INFERENCE]` We have **none** of them.

---

## B. ITEM DATA MODEL

| # | Field | Class | SS | FI | IX | Notes |
|---|---|---|---|---|---|---|
| B1 | Category (top-level) | [C] | ✅ | ✅ (6 groups) | ✅ (10) | |
| B2 | **Sub-category / leaf garment type** | [C] | ◐ registry exists, **live-inert** (`BL-132`) | ✅ ~70 leaves **with line icons** | ✅ ~76 leaves, text only | |
| B3 | Colour | [C] | ✅ single | ✅ ~30 + patterns + custom picker | ✅ 21, **multi-select** | Indyx's multi-colour is more correct |
| B4 | **Pattern** | [D] | ✅ registry (SS-036) | ✅ (inside colour picker: leopard/zebra/camo) | ◐ | |
| B5 | **Material / fabric** | [D] | ✅ registry (SS-036) | ✅ ~35 **with photographic texture swatches** | ✅ dropdown + `Natural/Synthetic/Semi-synthetic` rollup | |
| B6 | **Season** (multi) | [C] | ❌ | ✅ 4 w/ emoji | ✅ 4 | **We lack this entirely** |
| B7 | Brand | [C] | ❌ | ✅ + custom brands | ✅ **required** | |
| B8 | Size | [C] | ❌ | ✅ | ✅ required on edit | |
| B9 | Purchase price | [C] | ✅ (`purchase_price`) | ✅ | ✅ | |
| B10 | **Original price (MRP)** | [D] | ❌ | ❌ | ✅ | enables "discount captured" — **very India-relevant** |
| B11 | Purchase date / date acquired | [C] | ◐ | ✅ | ✅ | |
| B12 | **Purchase location** | [D] | ❌ | ❌ | ✅ | |
| B13 | **Source** (purchase/gift/self-made) | **[D]** | ❌ | ❌ | ✅ | India: + inherited, + tailored |
| B14 | **Secondhand flag** | [D] | ❌ | ❌ | ✅ | |
| B15 | **Condition + condition details** | [D] | ❌ | ❌ | ✅ | resale prerequisite |
| B16 | **Origin (country of manufacture)** | [D] | ❌ | ❌ | ✅ | |
| B17 | **Resale value / sold price / date sold** | **[U]** | ❌ | ❌ | ✅ | full lifecycle |
| B18 | Shopping URL / links | [D] | ❌ | ✅ | ✅ | affiliate hook |
| B19 | **Personal note** (private) | [D] | ❌ | ✅ | ✅ | |
| B20 | Description (objective) | [D] | ❌ | ◐ | ✅ | |
| B21 | **User hashtags** (searchable) | **[D/M]** | ❌ | ✅ (managed tags) | ✅ free-text | **taxonomy escape valve — mine these** |
| B22 | Favourite | [C] | ❌ | ✅ | ✅ | |
| B23 | **Archive** (hidden, stats retained) | [C] | ❌ | ✅ | ✅ | |
| B24 | **`DO NOT STYLE`** (exclude from suggestions) | **[U]** | ❌ | ❌ | ✅ | **cheapest quality lever in the category** |
| B25 | Private (item-level visibility override) | [D] | ❌ | ✅ | ✅ | |
| B26 | **Location / multi-home** | **[U]** | ❌ | ❌ | ✅ | **huge India fit** |
| B27 | Wear count | [C] | ✅ | ✅ | ✅ editable | |
| B28 | **Cost per wear (computed)** | [C] | ✅ computed column | ✅💰 | ✅ | |
| B29 | **Occasion-attributed wear history** | **[U — ours]** | ✅ (SS-035) | ❌ | ❌ | **we are ahead here** |
| B30 | "Outfits this item appears in" view | [D] | ❌ | ◐ | ✅ | |

**Score: StyleSense 8/30 · Fits 21/30 · Indyx 28/30.**

---

## C. ORGANISATION, FILTER & SEARCH

| # | Feature | Class | SS | FI | IX | Others |
|---|---|---|---|---|---|---|
| C1 | Category chip rail | [C] | ✅ | ✅ | ✅ | all |
| C2 | Text search | [C] | ✅ | ✅ | ✅ (brand/category/hashtag) | most |
| C3 | Filter sheet | [C] | ✅ | ✅ | ✅ | most |
| C4 | Filter by colour swatch | [C] | ◐ | ✅ | ✅ | most |
| C5 | Filter by season | [C] | ❌ | ✅ | ✅ | most |
| C6 | Filter by brand | [C] | ❌ | ✅ | ✅ | most |
| C7 | Filter by material | [D] | ❌ | ✅ | ✅ | few |
| C8 | **Filter by usage** (`used in outfits` / `not used`) | **[D]** | ❌ | ✅ | ✅ | rare |
| C9 | **Filter by source / secondhand / sold-donated** | [D] | ❌ | ❌ | ✅ | Indyx only |
| C10 | **Sort by cost-per-wear ▲▼** | **[D]** | ❌ | ◐ | ✅ | Indyx only |
| C11 | Sort by most/least worn | [D] | ❌ | ✅ | ✅ | few |
| C12 | **Group by** (tags/category/season/colour) | [D] | ❌ | ✅ | ◐ | rare |
| C13 | **Custom display** (items-per-row, primary label, default sort) | [D] | ❌ | ❌ | ✅💰 | Indyx only |
| C14 | **Faceted picker** (Category/Colour/Location/Season/Collection tabs w/ counts) | **[D]** | ❌ | ◐ | ✅ | Indyx only |
| C15 | Multi-select / bulk actions | [C] | ❌ | ✅ | ✅ | most |
| C16 | Active-filter count badge | [C] | ❌ | ◐ | ✅ | some |

---

## D. OUTFIT CREATION

| # | Feature | Class | SS | FI | IX | WH | AC | Others |
|---|---|---|---|---|---|---|---|---|
| D1 | Manual outfit from item picker | [C] | ◐ | ✅ | ✅ | ✅ | ✅ | all |
| D2 | **Free-canvas collage** (drag/scale/rotate/z-order) | [C] | ❌ | ✅ | ✅ | ✅ | ✅ | most |
| D3 | **Dressing Room — on-body mannequin compositing** | **[U/M]** | ❌ | ✅ | ❌ | ❌ | ◐ | **Fits only** |
| D4 | **Swipe-to-swap a garment slot in place** | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | Fits only |
| D5 | **Per-slot shuffle 🔀** | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | Fits only |
| D6 | **Whole-outfit shuffle** | [D] | ❌ | ✅ | ❌ | ◐ | ◐ | few |
| D7 | **Per-item saved transform** (position persists across outfits) | **[U/M]** | ❌ | ✅ | ❌ | ❌ | ❌ | **the trick that makes D3 work** |
| D8 | **Layer panel with depth presets + half/half live preview** | **[U]** | ❌ | ✅ | ◐ (z-buttons) | ❌ | ❌ | Fits only |
| D9 | Lock element | [D] | ❌ | ✅ | ✅ | ◐ | ◐ | few |
| D10 | **Body-type selector** (gender × size × leg proportion, ~18 sprites) | **[U]** | ❌ | ✅ | ◐ (photo-based) | ❌ | ◐ | Fits only |
| D11 | **Hairstyle + hair-colour selector** | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | Fits only |
| D12 | **Generative AI try-on** | [D] | ❌ | ✅💰 | ✅💰 | 🔜 | ◐ | few |
| D13 | **Try-on background/location presets** | [D] | ❌ | ✅💰 | ❌ | ❌ | ❌ | Fits only |
| D14 | Custom prompt on generation | [D] | ❌ | ✅ | ❌ | ❌ | ❌ | Fits only |
| D15 | **Mirror-selfie as the outfit image** | [C] | ❌ | ✅ | ✅ | ✅ | ✅ | most |
| D16 | **Add inspiration image to an outfit** | **[U]** | ❌ | ❌ | ✅ | ❌ | ❌ | Indyx only |
| D17 | **Duplicate outfit** | [D] | ❌ | ❌ | ✅ | ◐ | ◐ | rare |
| D18 | **Switch renderer without rebuilding** (collage ↔ dressing room ↔ try-on) | [D] | ❌ | ✅ | ◐ (board↔selfie) | ❌ | ❌ | Fits |
| D19 | Outfit occasion tag | [C] | ✅ | ✅ | ✅ | ✅ | ✅ | most |
| D20 | Outfit caption / notes | [C] | ❌ | ✅ | ✅ | ✅ | ✅ | most |
| D21 | Outfit date binding (built *for* a date) | [D] | ❌ | ✅ | ✅ | ✅ | ✅ | most |
| D22 | **Outfit visibility** (everyone/only-me/hidden-but-counts-in-stats) | [D] | ❌ | ✅ | ✅ | ◐ | ◐ | few |
| D23 | **Outfit provenance** (`self` / `social` / `expert`) | **[U/M]** | ❌ | ❌ | ✅ | ❌ | ❌ | **Indyx only — schema decision** |
| D24 | **Outfit status** (`in-wardrobe` / `recommendation` / `wishlist`) | **[U/M]** | ❌ | ❌ | ✅ | ❌ | ❌ | Indyx only |
| D25 | **Wear history per outfit** | [D] | ◐ | ◐ | ✅ | ✅ | ◐ | few |

---

## E. SUGGESTION & AI SURFACES

| # | Feature | Class | SS | FI | IX | WH | AC | NV | CL |
|---|---|---|---|---|---|---|---|---|---|
| E1 | **Outfit suggestions by occasion** | [C] | ✅ | ✅ | ❌ | ◐ | ✅ | ✅ | ✅ |
| E2 | **Suggestions on the home screen, unprompted** | **[D]** | ❌ | ✅ | ❌ | ◐ | ✅ | ✅ | ✅ |
| E3 | **Weather-aware suggestions** | [C] | ◐ (SS-022) | ✅ | ◐ | ◐ | ✅ | ✅ | ✅ |
| E4 | **"Pairs you've never tried"** | **[D]** | ❌ engine can, no surface | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E5 | **"Not yet worn"** | [D] | ❌ | ✅ | ◐ (filter) | ◐ | ❌ | ❌ | ❌ |
| E6 | **"Ideas for your newest pieces"** | **[D]** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E7 | **Editorial theme rails** ("Easy Summer Tailoring") | **[D]** | ❌ | ✅ | ❌ | ❌ | ◐ | ❌ | ❌ |
| E8 | **AI stylist as 4 concrete jobs** (rate/colours/packing/gaps) | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E9 | Conversational stylist chat | [D] | ❌ | ✅ | ❌ | ❌ | ◐ | ◐ | ❌ |
| E10 | **Named/personified stylist ("Ezra")** | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E11 | **Rate my outfit** | [D] | ❌ | ✅ | ❌ | ❌ | ◐ | ❌ | ❌ |
| E12 | **Find my colours / palette analysis** | [D] | ❌ | ✅ | ❌ | ❌ | ✅ | ◐ | ❌ |
| E13 | **Wardrobe gap analysis** | [D] | ❌ | ✅ | ◐ | ◐ | ◐ | ❌ | ❌ |
| E14 | **Packing list generation** | [D] | ❌ | ✅ | ◐ (collection) | ✅ | ✅ | ❌ | ◐ |
| E15 | **Structured suggestion request form** (occasion + when + seed items + vibe + company + free text) | **[U]** | ◐ (occasion only) | ✅ | ❌ | ❌ | ❌ | ◐ | ❌ |
| E16 | **"Build around this item" (seed item)** | **[D]** | ❌ | ✅ | ❌ | ❌ | ◐ | ◐ | ❌ |
| E17 | **Vibe/mood axis** (confident/cozy/edgy…) | **[D]** | ❌ | ✅ | ❌ | ❌ | ❌ | ◐ | ❌ |
| E18 | **"Who you'll be with" social-context axis** | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E19 | **Explanation / reasoning for a suggestion** | [D] | ✅ (`ReasoningDisclosure`) | ✅ (captions) | ✅ (stylist notes) | ❌ | ◐ | ◐ | ❌ |
| E20 | **Colour-harmony scoring** | [D] | ✅ (`engine_v2_colour`) | ◐ | ❌ | ❌ | ◐ | ✅ | ❌ |
| E21 | **Diversity/exploration control (MMR)** | **[U/M]** | ✅ (SS-038) | ◐ (breadth slider = user-facing) | ❌ | ❌ | ❌ | ❌ | ❌ |
| E22 | **User-facing "recommendation breadth" control** | **[U]** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E23 | **Cost/effort tier dial (E0–E2)** | **[U/M — ours]** | ✅ (SS-039) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E24 | **Auto 7-day plan** | [D] | ❌ | ◐ | ❌ | ◐ | ◐ | ❌ | ✅ |
| E25 | **Capsule generation** | [D] | ❌ | ❌ | ◐ (collection type) | ◐ | ❌ | ❌ | ❌ |
| E26 | **Narration caching** | **[M]** | ✅ (mig. 019) | ✅ | — | — | — | ❌ | — |
| E27 | **Impression/outcome logging** | **[M]** | ✅ (SS-033) | ✅ (inferred) | ◐ | ✅ | ◐ | ◐ | ◐ |

> **We win E19–E21, E23, E26, E27 — the invisible engine row. We lose E2, E4–E18, E22, E24 — the entire visible surface row.** That asymmetry *is* the competitive problem.

---

## F. PLANNING & CALENDAR

| # | Feature | Class | SS | FI | IX | WH | AC | SB | CL |
|---|---|---|---|---|---|---|---|---|---|
| F1 | Outfit calendar | [C] | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| F2 | Day / month views | [C] | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| F3 | Week strip | [C] | ❌ | ✅ | ✅ | ◐ | ✅ | ◐ | ✅ |
| F4 | Plan a future date | [C] | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| F5 | **Planning auto-logs the wear (and updates CPW)** | **[D]** | ❌ | ✅ | ✅ | ✅ | ◐ | ◐ | ◐ |
| F6 | Per-day note | [D] | ❌ | ✅ | ◐ | ◐ | ◐ | ✅ | ◐ |
| F7 | Device-calendar sync | [D] | ❌ | ❌ | ◐ | ❌ | ✅ | ◐ | ❌ |
| F8 | **Outfit-first planner UI** (big card, not a tiny grid) | [D] | ❌ | ✅ | ◐ | ❌ | ❌ | ❌ | ✅ |
| F9 | Travel/packing planning | [D] | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ◐ |

**StyleSense: 0/9.**

---

## G. ANALYTICS & INSIGHTS

| # | Metric / view | Class | SS | FI | IX | WH | AC | SB |
|---|---|---|---|---|---|---|---|---|
| G1 | Item count / composition by category | [C] | ❌ | ✅ donut | ✅ bars w/ 0-rows | ✅ | ✅ | ✅ |
| G2 | **Composition by colour** | [D] | ❌ | ✅💰 | ✅ (% inside swatches) | ◐ | ◐ | ✅ |
| G3 | Composition by brand | [D] | ❌ | ✅💰 | ✅ | ◐ | ❌ | ✅ |
| G4 | Composition by season | [D] | ❌ | ✅💰 | ✅ | ◐ | ◐ | ✅ |
| G5 | **Wardrobe value / avg item price** | [C] | ❌ | ✅ | ✅ | ✅ | ◐ | ✅ |
| G6 | Highest-price item | [D] | ❌ | ✅💰 | ✅ | ◐ | ❌ | ✅ |
| G7 | **Cost per wear (aggregate)** | [C] | ◐ per-item only | ✅💰 | ✅ | ✅ | ◐ | ✅ |
| G8 | **Wardrobe usage %** ("you're using 31%") | **[D]** | ❌ | ✅ **free** | ✅ | ✅ | ◐ | ✅ |
| G9 | Worn last month / worn overall | [C] | ❌ | ✅💰 | ✅ | ✅ | ◐ | ✅ |
| G10 | **Never worn** | [C] | ❌ | ✅💰 | ✅ | ✅ | ◐ | ✅ |
| G11 | Most / least worn items | [C] | ❌ | ✅💰 | ✅ | ✅ | ◐ | ✅ |
| G12 | **Most / least VERSATILE items** (# distinct outfits) | **[U]** | ❌ | ❌ | ✅ | ❌ | ❌ | ◐ |
| G13 | **Source split** (purchase/gift/self-made) | [D] | ❌ | ❌ | ✅ | ◐ | ❌ | ❌ |
| G14 | **New vs secondhand** | [D] | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| G15 | **Material type** (natural/synthetic/semi) | **[D]** | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| G16 | **Longevity** (<1y / 1–3 / 3–5 / >5) | **[D]** | ❌ | ❌ | ✅ | ◐ | ❌ | ❌ |
| G17 | **Items added / sold-donated over 1M-3M-6M-1Y** | [D] | ❌ | ◐ | ✅ | ✅ | ❌ | ◐ |
| G18 | **Metric definitions exposed via `?` tooltips** | **[D]** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| G19 | Drill-down to leaf subcategory | [D] | ❌ | ◐ | ✅ | ◐ | ❌ | ✅ |
| G20 | **Style Score** | **[U — ours]** | ✅ (SS-021) | ❌ | ❌ | ❌ | ◐ | ❌ |

**StyleSense: 1.5/20. Indyx: 20/20.**

---

## H. COLLECTIONS

| # | Feature | Class | SS | FI | IX | Others |
|---|---|---|---|---|---|---|
| H1 | Named collections | [C] | ❌ | ✅ | ✅ | most |
| H2 | **Typed collections** | [D] | ❌ | ✅ (Wishlist/Packing/Custom) | ✅ (Packing/Wishlist/**Inspiration**/**Capsule**) | few |
| H3 | Wishlist item **not** in wardrobe stats | **[D]** | ❌ | ✅ (radio: wardrobe+collection vs collection-only) | ✅ (status field) | rare |
| H4 | Mixed items + outfits in one collection | [D] | ❌ | ✅ (tabs) | ✅ | few |
| H5 | AI output lands in a collection (packing list) | [D] | ❌ | ✅ | ◐ | rare |

---

## I. SOCIAL & SHARING

| # | Feature | Class | SS | FI | IX | WH | AC |
|---|---|---|---|---|---|---|---|
| I1 | Public profile / followers | [D] | ❌ | ✅ | ✅ | ✅ | ✅ |
| I2 | **Public *web* closet URL** | **[U]** | ❌ | ❌ | ✅ | ◐ | ❌ |
| I3 | Closet privacy states (closed/open/featured) | [D] | ❌ | ◐ | ✅ | ◐ | ◐ |
| I4 | Likes / hearts | [C] | ❌ | ✅ | ✅ | ✅ | ✅ |
| I5 | **"Notify me about this item" bell on others' items** | [U] | ❌ | ❌ | ✅ | ❌ | ❌ |
| I6 | **24h OOTD story** | [D] | ❌ | ✅ | ❌ | ◐ | ✅ |
| I7 | **Outfit Frames — branded social export templates** | **[U/M]** | ◐ (share cards SS-021/023) | ✅ | ❌ | ◐ | ◐ |
| I8 | WhatsApp as a first-class share target | [D] | ◐ | ✅ | ◐ | ◐ | ◐ |
| I9 | Community feed | [D] | ❌ | ✅ | ◐ | ✅ | ✅ |
| I10 | **Styled-together / collaborative styling** | [D] | ❌ | ✅ | ✅ (via stylists) | ◐ | ◐ |
| I11 | Referral / gift credit | [D] | ❌ | ◐ | ✅ | ◐ | ◐ |
| I12 | **Human stylist marketplace** | **[U/M]** | ❌ | ❌ | ✅💰 | ❌ | ❌ |

---

## J. ONBOARDING & PROFILE

| # | Feature | Class | SS | FI | IX | Others |
|---|---|---|---|---|---|---|
| J1 | Multi-step wizard | [C] | ✅ 4 steps | ✅ **~15 screens, 1 question each** | ◐ | most |
| J2 | Gender | [C] | ✅ | ✅ (4 incl. non-binary) | ✅ | most |
| J3 | DOB / age | [C] | ❌ | ✅ (13+ compliance framing) | ✅ (birth year) | most |
| J4 | **JTBD / motivation multi-select** | **[D]** | ❌ | ✅ (7 options, pre-checked) | ❌ | rare |
| J5 | **Style archetype picker via editorial PHOTOS** | **[U]** | ❌ chips only | ✅ 14 archetypes, 2-col photo grid | ◐ (quiz) | rare |
| J6 | **Recommendation-breadth slider w/ live halo viz** | **[U]** | ❌ | ✅ | ❌ | none |
| J7 | Shopping-frequency question | [D] | ❌ | ✅ | ◐ | rare |
| J8 | **Value-prop interstitials mid-funnel** (CPW teaching card) | **[D]** | ❌ | ✅ | ◐ | rare |
| J9 | **Pre-permission priming screens** (mock OS dialog + arrow) | **[D]** | ❌ | ✅ | ✅ (rationale list + no-sale promise) | rare |
| J10 | **Progress theatre** (named analysis steps that tick) | [D] | ❌ | ✅ | ✅ ("up to 20 seconds") | rare |
| J11 | **Style-profile reveal artefact** (radar chart) | **[D]** | ◐ (Style Score) | ✅ | ◐ | rare |
| J12 | **Seed wardrobe at the end of onboarding** | **[D]** | ❌ | ✅ | ❌ | rare |
| J13 | Style quiz / archetypes | [D] | ◐ (keywords) | ✅ | ✅ | some |
| J14 | **Style words (3 free-text)** | [D] | ❌ | ❌ | ✅ | rare |
| J15 | **Multi-week style course/workshop** | **[U]** | ❌ | ❌ | ✅ (8 weeks) | none |
| J16 | Body type | [D] | ❌ | ✅ (sprite matrix) | ✅ (photo) | few |
| J17 | Facial-feature / colour analysis | [D] | ❌ | ✅ | ❌ | few |
| J18 | Occasion priorities | [D] | ✅ (SS-007) | ◐ | ◐ | few |
| J19 | Budget range | [D] | ✅ | ◐ | ❌ | few |
| J20 | Favourite colours | [D] | ✅ | ◐ | ❌ | few |
| J21 | Granular preferences editor post-onboarding | [D] | ✅ (SS-007) | ✅ | ✅ | some |

> **We are strong on J18–J21 (preference depth) and weak on J4–J12 (funnel craft).** Our onboarding collects good data badly; theirs collects more data delightfully.

---

## K. PLATFORM, SETTINGS & TRUST

| # | Feature | Class | SS | FI | IX | Others |
|---|---|---|---|---|---|---|
| K1 | iOS + Android | [C] | ✅ | ✅ | ✅ | all |
| K2 | **Web** | [D] | ✅ | ❌ | ◐ (public closet only) | GW only |
| K3 | Dark mode | [C] | ❌ | ✅ (3-state) | ❌ | some |
| K4 | Multi-language | [D] | ❌ | ✅ 26 | ❌ | AC 8 |
| K5 | **Currency setting** | [C] | ✅ ₹ native | ✅ (INR supported) | ✅ (USD default) | some |
| K6 | Temperature unit | [C] | ❌ | ◐ | ✅ | some |
| K7 | Calendar start day | [C] | ❌ | ❌ | ✅ | some |
| K8 | **"App starts in" (default tab)** | [D] | ❌ | ✅ | ❌ | rare |
| K9 | **Public feature-request board** | [D] | ❌ | ✅ | ❌ | rare |
| K10 | Re-sync wardrobe | [C] | ❌ | ✅ | ✅ (clear cache) | some |
| K11 | Blocked users | [C] | ❌ | ✅ | ◐ | some |
| K12 | **Phone-OTP identity (+91)** | **[U — ours]** | ✅ | ❌ | ❌ (email) | none |
| K13 | **IST / en-IN / ₹ lakh-crore formatting** | **[U — ours]** | ✅ | ◐ | ❌ | none |

---

## L. THE INDIA COLUMN (nobody else has any of this)

| # | Feature | SS today | Anyone else |
|---|---|---|---|
| L1 | **Ethnic garment taxonomy** (kurta, kurti, saree, lehenga, salwar, churidar, palazzo, sherwani, dhoti, dupatta, blouse, anarkali, sharara…) | ❌ registry exists, content missing | **❌ none** |
| L2 | **Garment-SET modelling** (saree+blouse+petticoat = one outfit; kurta+salwar+dupatta must co-suggest) | ◐ (`BL-116` open) | **❌ none** |
| L3 | **Drape styles** (saree drape, dupatta drape) | ❌ | **❌ none** |
| L4 | **Indian occasion depth** (mehendi, sangeet, haldi, reception, puja, Diwali, Karva Chauth, office-festive, temple) | ✅ **registry is extensible + DB-driven** | ❌ none |
| L5 | **Indian seasons** (summer / monsoon / winter / festive) not Spring-Fall | ❌ | ❌ none |
| L6 | **Fabric semantics for climate** (cotton/linen/khadi for summer, silk/brocade for festive) | ✅ registry (SS-036) | ◐ generic |
| L7 | **Occasion-first, not season-first, ranking** | ✅ engine is occasion-keyed | ❌ none |
| L8 | **Never suggest white for weddings** etc. — culture rules | ✅ in CLAUDE.md, engine-enforceable | ❌ none |
| L9 | **Tailored/stitched provenance** (darzi-made, not bought) | ❌ | ❌ none |
| L10 | **Inherited / hand-me-down source** | ❌ | ❌ (Indyx has gift) |
| L11 | **Multi-home** (city flat vs parents' house for festive wear) | ❌ | ✅ Indyx (generic, not India-framed) |
| L12 | **Indian brand catalogue** | ❌ | ✅ **Indyx & Fits already cover Spykar/Snitch/Souledstore/Westside/Max** |
| L13 | **₹ / phone-OTP / WhatsApp-native sharing** | ✅ / ✅ / ◐ | ❌ |

> **L1–L3, L5, L9, L10 are unclaimed and unclaimable-by-them.** L12 is the one place where they are already ahead of us in India.

---

## M. Scorecard

| Area | SS | FI | IX | Gap severity |
|---|---|---|---|---|
| A. Ingestion | 6/17 | **15/17** | 13/17 | 🔴 |
| B. Item data model | 8/30 | 21/30 | **28/30** | 🔴 |
| C. Filter/search | 4/16 | 12/16 | **15/16** | 🔴 |
| D. Outfit creation | 2/25 | **21/25** | 15/25 | 🔴 |
| E. Suggestions & AI | **10/27** (engine) | **21/27** (surfaces) | 5/27 | 🔴 surfaces / ✅ engine |
| F. Planning | 0/9 | **8/9** | 8/9 | 🔴 |
| G. Analytics | 1.5/20 | 11/20 | **20/20** | 🔴 |
| H. Collections | 0/5 | 5/5 | **5/5** | 🟠 |
| I. Social | 1/12 | 8/12 | **9/12** | 🟠 |
| J. Onboarding | 7/21 | **17/21** | 12/21 | 🟠 |
| K. Platform/trust | 4/13 | **10/13** | 7/13 | 🟡 |
| **L. India** | **6/13** | 1/13 | 2/13 | ✅ **ours** |

**Totals (unweighted): StyleSense ~49.5/208 · Fits ~150/208 · Indyx ~139/208.**

**But the weighting matters more than the total:**
- Of our 49.5, a disproportionate share sits in **[M] moat-bearing** rows (E21, E23, E26, E27, B29, L4, L7, K12) — the ones that compound or are structurally hard to copy.
- Of their ~150, the overwhelming majority sits in **[C] commodity** rows — the ones any competent team ships in a quarter.

**Strategic conclusion: we are behind on the copyable and ahead on the compounding.** The plan in `07-EPICS-AND-TICKETS.md` closes the commodity gap fast and cheap, without spending the engine advantage that got us here.
