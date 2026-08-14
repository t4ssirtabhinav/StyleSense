# Competitive Analysis Part 6 — UI/UX Specification

**Derived from:** `03-FITS-TEARDOWN.md` (interaction model) + `04-INDYX-TEARDOWN.md` (information architecture, data density, editorial craft).
**Applies to:** every ticket in `07-EPICS-AND-TICKETS.md`. Each ticket references section numbers here rather than restating layout.

> **The design thesis in one line:**
> **Fits' interaction grammar, Indyx's information density, on StyleSense's existing Indian design tokens.**
> We do *not* adopt Fits' monochrome or Indyx's bone-and-forest palette. Our marigold/peacock/Playfair system is already more distinctive than either, and it is India-legible in a way a Berlin-black or SF-bone palette is not. **We are copying structure and rhythm, not colour.**

---

## 0. Current state, honestly

`mobile/components/ui/` has 13 primitives (Avatar, Badge, BottomSheet, Button, Card, CircularProgress, EmptyState, IconButton, Input, ProgressBar, Skeleton, Text) and a token set in `tailwind.config.js`. That's a competent foundation — the problem is not the primitives, it's that **we render cards containing garments instead of rendering garments**, and every screen is a form rather than a composition.

Three structural mistakes to fix everywhere, before any new feature:
1. **Chrome around items.** `ItemCard.tsx` wraps a garment in a bordered card. Fits/Indyx both lay cut-outs directly on the page. → §2.1
2. **Blocking flows.** `ProcessingStep.tsx` blocks the user during background removal. Fits uses a dismissible toast. → §3.4
3. **One CTA style everywhere.** We need the black-pill discipline: exactly one primary action per screen, full-width, pinned. → §1.4

---

## 1. FOUNDATIONS

### 1.1 Colour tokens — extend, don't replace

Existing (keep): `brand #E8A420` (marigold), `peacock #0D6B6E`, `emerald #2D6A4F`, `rose #C45B7C`, `dark/textPrimary #1A1714`, `surfacePrimary #FAFAF7`, `surfaceSecondary #F4F2ED`, `textSecondary #5A5550`, `textMuted #9A9590`, occasion colours.

**Add these, with strict semantics (the Fits lesson: colour must mean something):**

| Token | Value | Meaning — used for NOTHING else |
|---|---|---|
| `actionPrimary` | `#1A1714` | the single primary CTA per screen (our black pill) |
| `aiPaid` | `#7B5EA7` (aubergine) | **any action that spends credits.** Never decorative. India-appropriate purple, not Fits' lilac |
| `aiProcessing.a` / `.b` | `#F7C5D8` / `#B8E6DC` | the scan/shimmer overlay pair (our pink/mint equivalent) |
| `alarmSurface` / `alarmText` | `#FBE9E7` / `#B3261E` | waste/never-worn/high-CPW warnings |
| `successSurface` / `successText` | `#E6F4EA` / `#1E6B3A` | good CPW, high versatility |
| `selectRing` | `#1A1714` | 2px selected border |
| `unselectRing` | `#D9D5CF` | 2px hollow ring |
| `festive` | `#C8102E` + `brand` | festive-occasion accent pair (kumkum red + marigold) |
| `surfaceInverse` | `#121110` | dark-mode page bg |

**Rule:** `aiPaid` aubergine appears **only** next to a credit cost. If a user sees aubergine, money is involved. This single rule does more for trust than any privacy copy.

### 1.2 Type scale

| Role | Family | Size/weight | Use |
|---|---|---|---|
| Display | `PlayfairDisplay_700Bold` | 34/40 | screen H1, hero stats (₹ figures, CPW) — *our Indyx-equivalent editorial voice* |
| Section | `Poppins_600SemiBold` | 22/28 | rail headers with `›` |
| Title | `Poppins_600SemiBold` | 17/22 | row titles, CTA labels |
| Body | `DMSans_400Regular` | 15/22 | descriptions |
| Caption | `DMSans_400Regular` | 13/18 · `textMuted` | metadata, counts, "why we ask" lines |
| Numeric | `JetBrainsMono_700Bold` | tabular | analytics tables, counts |
| Hindi | `NotoSansDevanagari_400Regular` | — | any Devanagari string |

**Playfair for hero numbers is the single highest-leverage typographic move available to us** — it is exactly what makes Indyx's `$0.00` cost-per-wear feel like a considered artefact rather than a database field. Use it for: CPW, wardrobe value, usage %, Style Score, palette names.

### 1.3 Spacing, radius, grid

- Page margin `md` (16). Section vertical rhythm `lg` (24). Rail gutter `sm`–`md`.
- Radius: `md`(12) chips · `lg`(16) cards/tiles · `xl`(24) sheets · `pill` CTAs.
- **Grids:** items **3-col**, outfits **2-col**, collections **2-col**, analytics cards full-width.
- Item grid gutter: **8px**, and **no card background** — cut-outs on `surfacePrimary`.

### 1.4 Button discipline (the black-pill rule)

| Variant | Spec | Rule |
|---|---|---|
| **Primary** | `actionPrimary` fill, white label, full-width, 56pt, `pill`, pinned bottom with 16pt margins + safe area | **exactly one per screen** |
| Secondary | `surfaceSecondary` fill, `textPrimary` label, same geometry | 0–1 per screen |
| Tertiary | bare text, `textSecondary` | "Skip", "Not now" |
| **Paid AI** | `aiPaid` fill + ✨ + **always** a `Costs N credits` caption beneath | only with a credit cost |
| Disabled | `textMuted` fill | |

> Our current `Button` primary is `bg-brand` (marigold) with dark text. **Keep marigold for brand/affirmative moments (Save, Continue in onboarding) but introduce `actionPrimary` black for the dominant page CTA.** Marigold-on-everything is why the app reads as "basic" — a single accent used for all actions carries no hierarchy.

### 1.5 Sheets over screens

Any "pick one thing" task is a `BottomSheet`, never a route push. Standard anatomy:
```
┌ grab handle ─────────────────────────────┐
│  Clear            TITLE              ✕   │   ← Clear left, Done/✕ right
├──────────────────────────────────────────┤
│  [search field, if >12 options]          │
│  [content — grouped, sectioned]          │
├──────────────────────────────────────────┤
│  [ Clear selection ]  [ Done ]           │   ← pinned footer pair
└──────────────────────────────────────────┘
```

### 1.6 Selection states (one grammar app-wide)

| Context | Unselected | Selected |
|---|---|---|
| Row (list) | `surfaceSecondary`, no badge | white + 2px `selectRing` + filled ✓ disc right |
| Chip | transparent, `textSecondary` | `actionPrimary` fill, white label |
| Grid tile (photo) | plain | 2px `selectRing` + marigold wash `brand@12%` |
| Grid tile (item picker) | hollow ring top-right | filled ✓ disc top-right |
| Swatch | plain circle | 2px ring + 2px gap |
| Body sprite | plain | `brand` 2px border |

### 1.7 Iconography — the asset investment nobody talks about

Fits' polish is **~70 garment line icons + ~35 photographic fabric swatches + 15 hairstyles × 12 hair colours + ~18 body sprites**. This is the real cost of parity and it is *content*, not code.

**Our required asset library (scoped as its own ticket — see SS-052):**
- **~85 garment line icons**: ~70 Western equivalents + **15 Indian-specific** (kurta, kurti, saree, lehenga, choli, salwar, churidar, palazzo, dhoti, sherwani, Nehru jacket, dupatta, jutti, kolhapuri, bangles). Single stroke weight (1.5pt), 24pt grid, `textPrimary`.
- **~40 fabric texture swatches** as photos, incl. **khadi, chanderi, banarasi silk, chikankari, ikat, bandhani, block print, brocade, georgette, crepe, kanjeevaram**.
- **~30 colour swatches + 8 pattern textures** (leopard/camo/stripe/check + **paisley/floral-block/bandhani/ikat**).
- **~24 body sprites**: (2 gender presentations + neutral) × (S/M/L/XL) × (regular/short-leg/long-leg), drawn to South Asian proportions.
- **~18 hairstyles × 10 hair colours** incl. **long braid, oiled centre-part, bun with gajra, turban/pagdi, hijab**; darker shades ordered first.

**These are the placeholder art when an image is missing, too** — which is why they pay for themselves twice.

### 1.8 Motion & feedback

- **AI processing** = `aiProcessing` two-colour shimmer sweeping the subject, 1.2s loop. Never a bare spinner on an AI action.
- **Named progress steps** that tick sequentially (Fits §7.12): *Reading your photo → Removing background → Identifying the garment → Matching to your wardrobe*. Honest, teaching, and it makes 8s feel like craft.
- **Long generative waits** get an explicit estimate: "This usually takes about 20 seconds." (Indyx §11.7)
- Skeletons match final layout exactly. Reuse `Skeleton.tsx`.

### 1.9 Empty states — merchandised, never apologetic

Anatomy: **real garment photography or the fanned 3-card illustration** → `Section`-size headline → one-sentence `Body` explaining the value → **one primary CTA**. Never a grey box with "No items".
Copy pattern from Indyx's first-run nudges — **one concrete instruction**, not a category: *"Upload a kurta you might wear this week and let's get started."*

### 1.10 Dark mode

Currently absent; a Fits table-stakes feature (3-state: System/Light/Dark). On dark, the primary pill **inverts to white-on-black**. Define every token in both modes at the Tailwind layer, never per-component.

### 1.11 India-specific UI rules

1. **₹ always via `en-IN`** — `₹1,23,456`, never `₹123,456`. Applies to every analytics figure.
2. **Dates `en-IN` / `Asia/Kolkata`**; week starts **Sunday** by default, user-overridable.
3. **Seasons are `Summer / Monsoon / Winter / Festive`**, not Spring/Fall. Monsoon gets its own icon and drives fabric rules.
4. **WhatsApp is the first share target**, before Instagram.
5. **Devanagari-safe layouts** — never fix a label's height; Devanagari ascenders/descenders exceed Latin.
6. **Low-end device budget** — item grids must virtualise via `FlashList`; the Dressing Room canvas caps at ~12 layers.

---

## 2. SCREEN SPECIFICATIONS

### 2.1 Wardrobe grid (redesign of `WardrobeGrid` + `ItemCard`)

```
┌────────────────────────────────────────────┐
│ Wardrobe                    🔍  ⚙   ◔      │  app bar: search, filter, insights
│ ┌────────────────────────────────────────┐ │
│ │ All  Tops  Bottoms  Ethnic  Shoes  ... │ │  chip rail (scroll) + [⚙ filter] pinned right
│ └────────────────────────────────────────┘ │
│                                            │
│    [cut-out]    [cut-out]    [cut-out]     │  3-col, NO cards, NO labels,
│                                            │  8px gutter, natural heights
│    [cut-out]    [cut-out]    [cut-out]     │
│                                            │
│                    ⊕                       │  FAB
└────────────────────────────────────────────┘
```
**Changes from today:** remove card background/border/shadow; remove the name label (identity is the image); let heights vary; add the pinned filter disc with an **active-filter count badge**; long-press → multi-select mode.

### 2.2 Filter sheet (composite of Fits §4.3 + Indyx §7.7 — this is the highest-value single screen to build)

Sections, in order:
| Section | Control |
|---|---|
| **Colours** | horizontal swatch rail, multi-select |
| **Categories** | `Select categories ›` → category sheet |
| **Season** | 4 pills: ☀️ Summer · 🌧 Monsoon · ❄️ Winter · ✨ Festive |
| **Occasion** | `Select occasions ›` (from our registry — **our differentiator, put it high**) |
| **Brands** / **Fabrics** / **Patterns** | `Select … ›` |
| **Usage** | `All` · `Not used in outfits` · `Used in outfits` |
| **Status** | `Favourite` · `Not yet worn` · **`Do not style`** · `Archived` · `Sold/Donated` |
| **Location** | `All` · `Here` · `Parents' home` · … |
| **Sort by** | Date added · Most worn · Least worn · **CPW highest** · **CPW lowest** · Category · Colour |
| **Group by** | None · Category · Colour · Season · Tag |
Footer: `Clear filters` / **`Apply`**.

### 2.3 Item detail (redesign of `ItemDetailSheet`)

Becomes a **full route** with tabs, not a sheet:
```
‹  Item                                  🗑
[hero image, paged: original / cut-out / enhanced]
[SD|HD]                            [✨ Enhance]
[+ Add image] [worn-shot thumb] [ ... ]
┌──────────┬──────────────┬──────────┐
│ COST/WEAR│ DETAILS      │ TAGS     │
└──────────┴──────────────┴──────────┘
```
- **COST/WEAR tab:** hero `₹—` in Playfair + "worn N times in M days"; then Times worn · Source · Secondhand · Date acquired · Purchase price · **MRP** · Purchase location · Resale value · Date sold/donated · Sold price.
- **DETAILS tab:** Brand · Name · Category · Garment type · Size · Colour(s) · Fabric · Pattern · Personal note · Description · Condition · Shopping URL.
- **TAGS tab:** Season · Occasions · Status pills (Favourite / **Do not style** / Archive / Private) · Location · **Custom hashtags** (free text, searchable).
- Bottom: **"Appears in N outfits ›"**.

### 2.4 Add-clothes hub

Horizontal source chips: **Camera · Gallery · Search catalogue · Scan photos · Forward receipt**, then a search field ("Search for clothes") with **Popular searches** seeded to India (`white kurta`, `black formal trousers`, `blue jeans`, `white sneakers`, `Nehru jacket`, `banarasi saree`, `kolhapuri chappals`, `Snitch shirt`).
Followed by the **photo-quality coaching sheet** (§3.3) on first use.

### 2.5 Home (complete rewrite)

```
┌────────────────────────────────────────────┐
│ StyleSense              ⭐Upgrade  🔔  🔍   │
│                                            │
│ ┌────────────────────────────────────────┐ │
│ │  TODAY · 32°C ☀️ · Thursday            │ │  full-bleed paged suggestion cards
│ │  [rendered outfit]                     │ │  caption: "Light cotton office look
│ │  ‹ ● ○ ○ ›                             │ │   for a hot Thursday"
│ └────────────────────────────────────────┘ │
│                                            │
│ Your Stylist                            ›  │  4 photo action tiles:
│ [Rate my fit][My colours][Pack][Gaps]      │  horizontally scrolling
│                                            │
│ Pairs you've never tried                ›  │  ← engine preset rail
│ [outfit][outfit][outfit]                   │
│                                            │
│ Not yet worn                            ›  │  ← WHERE wear_count = 0
│ [item][item][item][item]                   │
│                                            │
│ Ideas for your newest pieces            ›  │
│ Festive picks                           ›  │  ← INDIA-ONLY RAIL
│ Recent outfits                          ›  │
│ Recently added                          ›  │
├────────────────────────────────────────────┤
│      Home        ⊕        Profile          │  3-slot floating tab bar
└────────────────────────────────────────────┘
```
**Rules:** every section header ends `›` and opens a full page. Every rail is horizontal. Home never scrolls more than ~6 screens. Rails read from the precomputed `suggestion_rails` table (see `08-CHEAP-SUGGESTION-ENGINE.md` §5.2), so Home is one query.

### 2.6 Outfit Studio (the flagship — Fits §5)

**Step 1 — pick items**
```
‹    🌦 32°/26°C          📅 Today
[ 👤 Selfie ]        [ ✨ Suggest ]
[All][Tops][Bottoms][Ethnic][Shoes] ⚙
[3-col grid, ring/✓ badges]
─────────────────────────────────────
3 selected  [thumb ✕][thumb ✕][thumb ✕]
[ Collage ⌃ ]                [ Next → ]
```
**Step 2 — mode selector sheet:** three photo tiles — **Collage** (free) · **Dressing Room** (free) · **AI Try-On** (`aiPaid` + credits).

**Step 3 — Dressing Room canvas**
```
┌─────────────────────────────────┐
│                          [👤]   │  body/avatar settings
│      ╭─────────╮         [👕]   │  layers
│      │mannequin│         [🔀]   │  shuffle whole outfit
│      │+garments│                │
│      ╰─────────╯                │
│  ◄ swipe a slot to swap ►       │
├─────────────────────────────────┤
│ [Kurta][Shirt][Tee][Polo] ⚙     │  slot-scoped type rail
│ [ Switch to… ]      [ Next → ]  │
└─────────────────────────────────┘
```
- Tap a garment → right-edge vertical stack: **✓ · ✥ (move/scale) · 🔓 (lock) · 🔀 (swap this slot) · 🗑**.
- **Per-item transform persists** (`wardrobe_items.render_transform` JSONB) — one-time fiddling per garment, reused forever. *This is the mechanic that makes it look good; without it the feature fails.*
- **Layers panel**: drag-reorder rows + 4 depth-preset icons + **half/half live preview** on the mannequin.
- **Ethnic handling (our differentiator):** a saree renders as a **drape sprite** with the blouse layered beneath; a dupatta gets its own **drape-style picker** (front-pallu / shoulder / both-shoulders / head-covered). No competitor can render this at all.

**Step 4 — Save sheet**
Caption · **Date** · **Occasion** · Visibility (Everyone / Only me / **Hidden but counts in stats**) · Save to collection · toggle **Share as today's fit (24h)**.

### 2.7 Planner
Tabs **Day | Month**. Week strip with a dot under days that have an outfit. Day view = one **large paged outfit card** (peeking prev/next) + "Add a note…" + `⋯`. **Assigning an outfit to a past-or-today date logs the wear and updates CPW** — state this in the UI: *"Logged · cost per wear now ₹142"*.

### 2.8 Insights
Tabs **`Composition | Usage | Value`**. Every card carries a **`?`** revealing the metric's exact definition and exclusions (Indyx §10.3 — copy this discipline).
- **Composition:** category bars (**show 0-rows**), colour grid with % *inside* each swatch, fabric natural/synthetic donut, season donut, **`Undefined` always shown as a slice**.
- **Usage:** `Wardrobe usage NN%` hero (free), most/least worn, **most/least versatile** (`COUNT(DISTINCT outfit_id)`), never worn, worn last 30 days, a `# of wears | CPW` table by category and by colour.
- **Value:** wardrobe value, average item price, highest price, **CPW leaderboard**, MRP-vs-paid "you saved ₹X", items added/sold over 1M/3M/6M/1Y.
- Hero numbers in **Playfair**, ₹ in `en-IN`.
- **Free/paid split (from Fits §6.3):** the *anxiety* metric is free (`usage %`, `never worn` count); the *resolution* metrics are paid (which items, CPW detail, value).

### 2.9 Onboarding (rewrite to the one-question-per-screen funnel)

Order (Fits §1, adapted):
1. Gender (auto-advance) → 2. **What do you want most from StyleSense** (multi, pre-checked) → 3. **Style archetypes via photo grid** — *Indian archetypes: Classic Indian · Indo-Western · Minimal · Streetwear · Old Money · Ethnic Formal · Smart Casual · Bold Festive · Relaxed · Athleisure · Corporate · Bohemian*, gender-matched photography → 4. **Recommendation-breadth slider with the live halo** (maps directly to our MMR λ) → 5. City (weather) → 6. **Occasion priorities** (our registry — keep, it's our edge) → 7. Budget → 8. Favourite colours → 9. **Value-prop interstitial: cost-per-wear** (the ₹ scoreboard, taught before they have data) → 10. Body type → 11. Optional selfie (framed as *both* try-on and colour analysis) → 12. **Seed wardrobe: "Add suggested pieces"** (India staples, pre-checked) → 13. Progress theatre → 14. **Style-profile reveal (radar chart)**.

Every screen: thin top progress bar · Playfair H1 · one-line grey **"why we ask"** · answer surface · one pinned CTA. Single-select auto-advances.

### 2.10 Stylist hub
Four photo action tiles (not a chat box): **Rate my fit · Find my colours · Pack for a trip · Find gaps**. Each opens a **structured form**, not a prompt field:
`Occasion` · `When` · `Style around these items` · `Vibe` · `Who you'll be with` · `Anything else` → `✨ Make outfits`.
Chat exists behind these as one surface, but the form is the primary path — it keeps prompts short, cheap, and cacheable (`08-…` §3).

### 2.11 Outfit Frames
Templates: **OOTD** · **Credits** (lists every piece + brand) · **Product grid** · **Festive frame** (marigold/rangoli border). Every export carries `@handle · StyleSense`. Share row: **Save · WhatsApp · Instagram · More**.

---

## 3. INTERACTION PATTERNS (reusable)

| # | Pattern | Spec |
|---|---|---|
| 3.1 | **Rail** | `Section` header + `›`, horizontal `FlashList`, peek the next card ~16pt, full page on tap |
| 3.2 | **Pre-permission priming** | full screen: illustration → why (3 bullets) → **explicit no-sale promise** → CTA that triggers the real dialog. Never call the OS dialog cold. (Indyx §7.8 is the best-in-class version) |
| 3.3 | **Quality coaching** | bottom sheet, 3 labelled examples with 😍/🙂/🙁 verdict badges, "Got it 👌" |
| 3.4 | **Background work** | dark floating toast above the tab bar: thumb + "Removing background…" + "N/M completed" + ✕. **Never block.** |
| 3.5 | **Paid AI action** | `aiPaid` pill + ✨ + `Costs N credits` + balance `N ⊕` + optional "Add instructions" |
| 3.6 | **Blur-tease** | free users see item 1; items 2..N blurred with 🔒 and "Unlock N more" |
| 3.7 | **Generated artefact** | named + branded card + ⬇/⬆ + a free "% of your wardrobe" stat + a prose "why" |
| 3.8 | **Confirm dialog** | rounded card, filled destructive CTA on top, outlined "Go back" below |
| 3.9 | **Multi-select** | long-press enters mode; nav bar becomes `Cancel` / `N selected` / `Done`; action bar rises |
| 3.10 | **Metric tooltip** | `?` disc next to every derived metric revealing formula + exclusions |

---

## 4. COMPONENT BACKLOG (additions to `components/ui/`)

| Component | Notes |
|---|---|
| `ChipRail` | scrollable chips + pinned trailing action disc + count badge |
| `ItemTile` | chrome-less cut-out, optional selection badge, icon fallback |
| `OutfitCard` | composed render + caption + occasion chip + ♡ |
| `RailSection` | header + `›` + horizontal list + empty state |
| `FilterSheet` | the §2.2 composite |
| `SwatchGrid` / `SwatchRail` | colours + patterns + custom |
| `FabricSwatch` | photographic texture tile |
| `GarmentIcon` | the ~85-glyph set, also the image fallback |
| `SegmentedTabs` | Items/Outfits/Collections with counts |
| `StatTile` / `MetricCard` | Playfair hero number + `?` tooltip + optional 🔒 |
| `DonutChart` / `BarRow` / `SwatchPercentGrid` | analytics primitives — **load the `dataviz` skill before building these** |
| `CreditPill` | `aiPaid` + cost + balance |
| `ProcessingToast` | §3.4 |
| `NamedProgress` | ticking step list |
| `PermissionPrimer` | §3.2 |
| `BodySprite` / `HairstylePicker` | avatar assets |
| `Canvas` + `TransformToolbar` + `LayerPanel` | Dressing Room |
| `WeekStrip` / `DayOutfitCard` | planner |
| `ShareFrame` | export templates |
| `BreadthSlider` | halo visualisation |
| `RadarChart` | style profile |

---

## 5. Accessibility & performance floor
- Every icon-only control gets `accessibilityLabel`; touch targets ≥44pt.
- Contrast ≥4.5:1 for body text in both themes — **check marigold-on-white; `#E8A420` on `#FAFAF7` fails for text** and must only be used as a fill behind dark text (which our `Button` already does correctly).
- Selection is never colour-only — always a shape change (ring/✓) too.
- `FlashList` for every grid/rail. Cut-outs served as WebP with a thumbnail derivative; never full-res in a grid.
- Dressing Room: cap layers, memoise transforms, run gestures on the UI thread (Reanimated worklets).
- Respect `prefers-reduced-motion` — shimmer degrades to a static tint.
