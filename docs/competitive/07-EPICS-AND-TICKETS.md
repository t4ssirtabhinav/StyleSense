# Competitive Analysis Part 7 — Epics, Tickets & Sequencing

**Rewritten 2026-08-20** — the venture premise behind the original 30-ticket plan is dead (Google Photos Wardrobe shipped a free, India-launch-day competitor to the cataloguing layer this whole category monetised; see the "Google Wardrobe" thread in this conversation, not yet written up as its own doc). This is not a repricing exercise — it's a scope cut to what remains true: **build a genuinely good, technically interesting app for a portfolio, at whatever pace works, no revenue assumption, no race.**

**Derived from:** `02-FEATURE-MATRIX.md` (what's missing) · `06-UIUX-SPEC.md` (how it looks) · `08-CHEAP-SUGGESTION-ENGINE.md` (how it stays cheap).
**Ticket IDs:** `SS-040`–`SS-069` remain reserved for this doc per `docs/BACKLOG.md`'s ID-reservation notice. Only the 8 below are promoted; the rest are released back — **do not treat SS-040–069 as reserved beyond the 8 listed**, a real new ticket may reuse a number from the cut list if it's a genuinely different scope.
**Process unchanged:** promote a ticket below to `docs/tickets/raw/SS-0XX.md`, run `/ticket SS-0XX` through architect→developer→qa→devops. `Risk:` still decides the lane.

---

## What changed and why

| Cut from the plan | Why |
|---|---|
| Monetisation (`SS-069`), Razorpay, credit packs | Nothing to charge for — free-and-bundled-in-the-OS beats any consumer price we could set. Building a paywall doesn't demonstrate anything a recruiter values either. |
| Resale marketplace, stylist marketplace | Two-sided-supply businesses. Not in scope for a solo portfolio project regardless of Google. |
| Social/growth (`SS-066`–`068`), public web closet | Distribution-growth features only matter if there's a business to grow. Cut, not because they're hard — because they're pointless without users to acquire. |
| Photo-library mining (`SS-060`) | Google's OS-level version makes this a worse rebuild of a system feature. Not an interesting engineering problem anymore either. |
| Receipt-email ingestion (`SS-061`), catalogue search (`SS-059`) | Ingestion-funnel optimisation only matters at scale. Cut. |
| Colour analysis (`SS-065`), image enhancement (`SS-063`), outfit frames (`SS-066`) | Nice-to-haves that don't teach new skills over what's already in scope. |
| Onboarding funnel rewrite (`SS-064`), item detail polish (`SS-041`), filter overhaul (`SS-042`), grid polish (`SS-043`) | Real gaps, genuinely low-signal to build first. Revisit after the 8 below, if the project still has momentum. |

**What's kept, and why each one earns its place as a portfolio artifact:**

1. **`SS-044`** fixes a real, already-found, already-documented bug (`BL-132`) where tested scoring logic is silently inert in production — this is the single best "I debug systems" story available and it was already true before any of this week's news.
2. **`SS-040`** (trimmed) is real data modeling: lifecycle/cost-per-wear fields, `do_not_style` wired into the eligibility stage, not just columns added and ignored.
3. **`SS-048`/`SS-049`** turn an already-built deterministic engine into something a user (or an interviewer) can actually see working — this is the difference between "I wrote a scoring algorithm" and "I shipped a feature."
4. **`SS-055`/`SS-056`** are the flagship frontend showpiece — gesture handling, persisted transforms, a finite sprite system, zero backend AI dependency. The best demo-able 30 seconds in the app.
5. **`SS-057`** is cheap (3 pts) and is the one schema decision (`source`/`status` on outfits) that's expensive to retrofit later — keep it while it's still free.
6. **`SS-052`** is a real analytics/SQL exercise (versatility, cost-per-wear, composition) — a different skill than the engine or the UI work, worth having in the portfolio.

---

## The eight kept tickets

### SS-044 — Indian Garment Types & Category Migration
`[Infra]` `[P0]` `[5 pts]` · **`Risk: high`** · **resolves `BL-132`** · **build this first**
Migrate live `wardrobe_items.category` (21-value enum, still in use) onto the `garment_types` registry keys seeded by SS-034, and extend the registry with the Indian vocabulary (kurta, kurti, anarkali, sherwani, saree, lehenga, salwar, churidar, palazzo, dhoti, dupatta, jutti, etc. — full list in the original spec, unchanged). Each type gets `coverage`, `formality`, `layer_depth`, `volume`, `register` populated — the attributes `engine_v2_attribute_scoring` already reads but currently gets nothing for.
**AC:** every live wardrobe row resolves to a `garment_type`; `volume_balance` and `register_coherence` produce non-neutral scores on a real wardrobe (verify against live data, not fixtures); backfill is reversible.
See `docs/tickets/raw/SS-044.md` for the full promoted spec.

### SS-040 — Item Lifecycle & Cost-Per-Wear Schema *(trimmed)*
`[Infra]` `[P0]` `[3 pts]` · **`Risk: high`** (schema + RLS)
Trimmed from the original 20-column version to what actually gets used by SS-052/SS-055/SS-057: `brand`, `purchase_price`, `date_acquired`, `condition`, `do_not_style`, `is_favourite`, `is_archived`, `custom_tags[]`, `render_transform` (JSONB, for SS-055). **`do_not_style` must be wired into `engine_v2_eligibility`, not just added as a column** — cheapest suggestion-quality feature in the category and worthless unread.
**AC:** all columns nullable + RLS-covered; regenerated `types/supabase.ts`; `do_not_style` items excluded by the eligibility stage, asserted by test.

### SS-048 — Rail Presets & Precompute
`[Infra]` `[P0]` `[4 pts]` · `Risk: med` · depends SS-044
`suggestion_rails` table `(user_id, rail_key, computed_at, payload jsonb)`. Presets over `EngineV2.generate_portfolio`: `todays_picks`, `never_tried_pairs`, `not_yet_worn`, `newest_pieces`. Nightly + on-write-debounced precompute.
**AC:** serving a rail is one indexed read; zero AI provider calls in the E0 path, asserted by test.

### SS-049 — Home Screen Rewrite
`[Feature]` `[P0]` `[4 pts]` · `Risk: low` · depends SS-048
Per `06-UIUX-SPEC.md` §2.5, trimmed to what SS-048 actually serves: a day suggestion card + the four rails. No paywall teasing, no monetisation-shaped UI.

### SS-055 — Dressing Room (on-body compositing)
`[Feature]` `[P0]` `[8 pts]` · `Risk: med` · depends SS-044, SS-040 (`render_transform`)
Per `06-UIUX-SPEC.md` §2.6: mannequin + garments as z-ordered transparent PNGs; per-item persisted `render_transform`; tap-and-swipe slot swap; per-slot shuffle.
**AC:** zero network calls to render; swap is <100ms; transforms persist across outfits.
> Still worth doing the ethnic-drape case (saree/dupatta) — it's the most technically interesting rendering problem in the whole plan and has no off-the-shelf answer, which is exactly what makes it a good portfolio piece regardless of market position.

### SS-056 — Body Type & Avatar
`[Feature]` `[P1]` `[3 pts]` · `Risk: low` · depends SS-047 *(asset library — trim to what SS-055/056 actually need, don't build the full ~85-icon library up front)*
Finite indexed sprite matrix (gender presentation × size × leg proportion) + hairstyle picker. No ML, no measurements.

### SS-057 — Save Outfit, Occasions, Visibility & Collections
`[Feature]` `[P1]` `[3 pts]` · `Risk: low`
Save sheet; outfit gets `source` (`self|ai|expert|social`) and `status` (`owned|recommendation|wishlist`).
> Add these two columns now even though nothing reads them yet — cheap today, a real migration on a grown table later.

### SS-052 — Wardrobe Insights (Composition / Usage / Value)
`[Feature]` `[P1]` `[5 pts]` · `Risk: low` · depends SS-040
Per `06-UIUX-SPEC.md` §2.8. **Load the `dataviz` skill before writing any chart code.** Must include versatility (`COUNT(DISTINCT outfit_id) GROUP BY item_id`).
**AC:** every metric card states its formula and exclusions; ₹ in `en-IN`.

---

## Sequencing

**Phase 1 — engine correctness (do this first, it's the strongest single résumé line):**
`SS-044` → `SS-040`

**Phase 2 — make the engine visible:**
`SS-048` → `SS-049`

**Phase 3 — the flagship UI:**
`SS-056` → `SS-055` → `SS-057`

**Phase 4 — round it out:**
`SS-052`

No wave deadlines — this is an ongoing side project. Each phase is independently demoable; stopping after any phase still leaves something real to show.

---

## Everything cut

All of `SS-041`, `042`, `043`, `045`, `046`, `047` (full version), `050`, `051`, `053`, `054`, `058`–`069` are released — not scheduled, not reserved. If the project's direction changes again, re-derive scope from `05-GAP-ANALYSIS.md`'s feature matrix rather than assuming these drafts still apply; several (`SS-058` seed wardrobe, `SS-045` garment sets) are still good ideas and worth reviving specifically, just not now.

The `BL-151`…`BL-158` backlog rows proposed by the original version of this doc are **not** being logged — they were scoped to tickets that are now cut. `BL-132` (the one that matters) was already logged independently and is unaffected by any of this.
