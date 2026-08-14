# Competitive Analysis — Index

**Completed:** 2026-08-13 · **Status: ✅ COMPLETE** — all 222 screenshots analysed, all 8 deliverables written.

## Read in this order

| # | File | What it answers |
|---|------|-----------------|
| **5** | [`05-GAP-ANALYSIS.md`](05-GAP-ANALYSIS.md) | **Start here.** Where we stand, what keeps us ahead, the 3 decisions this forces |
| 1 | [`01-MARKET-AND-BUSINESS.md`](01-MARKET-AND-BUSINESS.md) | Business models, pricing, funding, users, USP/moat per app; India market context |
| 2 | [`02-FEATURE-MATRIX.md`](02-FEATURE-MATRIX.md) | Exhaustive feature extraction across 10 apps, classified USP / Differentiator / Commodity / Moat |
| 8 | [`08-CHEAP-SUGGESTION-ENGINE.md`](08-CHEAP-SUGGESTION-ENGINE.md) | How they suggest outfits without per-request AI, and what we already have |
| 3 | [`03-FITS-TEARDOWN.md`](03-FITS-TEARDOWN.md) | Screen-by-screen teardown of Fits (135 shots) — the **interaction** benchmark |
| 4 | [`04-INDYX-TEARDOWN.md`](04-INDYX-TEARDOWN.md) | Screen-by-screen teardown of Indyx (87 shots) — the **data-model** benchmark |
| 6 | [`06-UIUX-SPEC.md`](06-UIUX-SPEC.md) | Tokens, components, screen specs, interaction patterns — the build spec |
| 7 | [`07-EPICS-AND-TICKETS.md`](07-EPICS-AND-TICKETS.md) | 9 epics, 30 draft tickets (SS-040…SS-069), 4 waves, parallelisation plan |

## Source material
- `c:\Users\abhia\Downloads\comp analysis\Fits\` — 135 screenshots (`IMG_7874`–`IMG_8018`) ✅ all analysed
- `c:\Users\abhia\Downloads\comp analysis\Indyx\` — 87 screenshots (`IMG_7785`–`IMG_7873`) ✅ all analysed
- https://www.nouva.app/blog/best-wardrobe-apps-2026-comparison ✅ fetched
- Web research: Whering, Acloset, Indyx, Fits, GetWardrobe, Alle, India market ✅
- Apps in scope: Whering, Acloset, GetWardrobe, Fits, Indyx, Nouva, Clueless, Stylebook, Pureple, Cladwell (+ StyleSense)

## Deliverables
| # | File | Status |
|---|------|--------|
| 1 | `01-MARKET-AND-BUSINESS.md` | ✅ |
| 2 | `02-FEATURE-MATRIX.md` | ✅ |
| 3 | `03-FITS-TEARDOWN.md` (135/135) | ✅ |
| 4 | `04-INDYX-TEARDOWN.md` (87/87) | ✅ |
| 5 | `05-GAP-ANALYSIS.md` | ✅ |
| 6 | `06-UIUX-SPEC.md` | ✅ |
| 7 | `07-EPICS-AND-TICKETS.md` | ✅ |
| 8 | `08-CHEAP-SUGGESTION-ENGINE.md` | ✅ |

## Headline findings
1. **We have the best engine and the weakest product.** ~49/208 on the feature matrix vs Fits ~150, Indyx ~139 — but our score sits in **moat-bearing** rows and theirs in **commodity** rows. Behind on the copyable, ahead on the compounding.
2. **`BL-132` is live and costly:** `engine_v2.py`'s own docstring records `volume_balance`/`register_coherence` as *"100% LIVE-INERT today"* because no live `wardrobe_items.category` resolves through `garment_types`. **We are running a degraded engine on real users.** This promotes the taxonomy migration (SS-044) into Wave 1.
3. **~95% of what users experience as "AI" in Fits is SQL + combinatorics + client-side compositing.** *"Pairs you've never tried"* is a `NOT EXISTS` clause with a copywriter. Our `engine_v2` already does the hard part; we lack the **surfaces**.
4. **India garment grammar (saree / kurta-set / dupatta as compositions, not items) is the only uncopyable moat available** — no competitor can represent it, and retrofitting means redesigning their outfit model for a market they don't serve.
5. **Indyx and Fits already carry Indian brands** (Spykar, Snitch, Souledstore, Westside, Max) and Fits already supports **INR** and 26 languages. **Our India claim cannot rest on brand coverage** — only on taxonomy, occasions and styling rules.

## Next actions
- Promote `SS-040` (rich item schema) and `SS-044` (taxonomy migration) to `docs/tickets/raw/` and run `/ticket SS-040` — full lane, `Risk: high`, serialised.
- Append `BL-151`…`BL-158` from `07-EPICS-AND-TICKETS.md` §Backlog to `docs/BACKLOG.md` **Active**.
