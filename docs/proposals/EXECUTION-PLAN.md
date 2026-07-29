# Execution Plan — Extensible Architecture Baseline (Tier A)

**Status:** Plan for approval. No tickets cut, no backlog rows written, no code changed.
**Date:** 2026-07-28
**Supersedes the sequencing in:** [`PLATFORM-CONSOLIDATION.md`](PLATFORM-CONSOLIDATION.md) §6 Tier A
**Companions:** [`PLATFORM-CONSOLIDATION-TECHNICAL.md`](PLATFORM-CONSOLIDATION-TECHNICAL.md) · [`PLATFORM-CONSOLIDATION-BUSINESS.md`](PLATFORM-CONSOLIDATION-BUSINESS.md)

**Standing assumption, per your instruction:** technical diligence TD-01…TD-05 is *assumed passed* so we can move. It is **not proven** — §3.4 explains how the architecture makes a negative result survivable without a rewrite. **TD-06 (Replicate re-pricing) is deprioritised** and stays open.

---

## 1. What this plan does, in one paragraph

We stop treating "cheap AI" and "extensible product" as two projects. They are the same project, because both are solved by **moving decisions out of code and into data**: occasions become rows instead of an enum, model choice becomes config instead of an import, styling rules become a shared module instead of prompt text, and cost becomes a logged number instead of a monthly surprise. That gives us the 8–35× unit-cost reduction *and* a product where adding Onam, Pongal, a Goa trip, a marathon, or a Griha Pravesh is an INSERT — not a migration, a release and an app-store review.

**We do this now because every one of these decisions is currently free and becomes expensive the moment SS-020 ships.**

---

## 2. The three findings that set this plan

### 2.1 The occasion model is a hard blocker on everything you described

You said the product isn't limited to weddings — Ganesh Chaturthi, Navratri, Onam, Pongal, Durga Puja, year-round regional weddings, travel, international travel, sports, fitness, events. **The current schema cannot express any of that.**

`[VERIFIED — read from the repo, 2026-07-28]` `occasion_type` is a **Postgres ENUM** with exactly 12 values, hardcoded in four places:

| Location | Form |
|---|---|
| [supabase/migrations/001_initial.sql:18](supabase/migrations/001_initial.sql#L18) | `CREATE TYPE occasion_type AS ENUM (...)` — 12 values |
| [mobile/features/wardrobe/wardrobe.constants.ts:104](mobile/features/wardrobe/wardrobe.constants.ts#L104) | `OCCASION_TYPES: OccasionType[]` — "transcribed verbatim" from the migration |
| [mobile/types/supabase.ts](mobile/types/supabase.ts) | generated TS union |
| `occasion_types` **table** (003_onboarding_taxonomies.sql) | a *different* object — 9 seeded rows, onboarding only |

Consequences, stated plainly:

- **Adding "Ganesh Chaturthi" today requires a DB migration + type regeneration + a TS constant edit + an app-store release.** A calendar-driven festival feature cannot ship on that.
- Postgres enums **cannot have values removed or reordered**, and **cannot carry metadata** — no region, no date rule, no formality, no styling rules, no tier gate.
- There is **no hierarchy**. `festival` and `puja` are siblings; Navratri is a festival *and* a 9-day series *and* regional. The enum cannot say any of that.
- There is already a **split brain**: a 12-value enum for tagging and a 9-row table for onboarding, with a 4-colour token map over the top. `BL-008` has been re-opened and re-deferred by four separate Architect passes (SS-004, SS-005, SS-013, and again since). **It is not a colour problem. It is this problem.**

**The good news:** the repo already established the right pattern. `003_onboarding_taxonomies.sql` says in its own comments that taxonomies "must not be hardcoded TS unions." SS-004 did it correctly for onboarding. **We are finishing a pattern the codebase already started, not inventing one.**

### 2.2 Your model-ladder instinct is right, and cheaper than I proposed

`[VERIFIED 2026-07-28 — ai.google.dev/gemini-api/docs/pricing]` Cost per **pre-filtered** suggestion call (≈800 input / 500 output tokens `[ESTIMATE]`):

| Model | $/MTok in/out | ₹/call | vs Sonnet |
|---|---|---|---|
| **Gemini 2.5 Flash-Lite** | $0.10 / $0.40 | **₹0.024** | **35× cheaper** |
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | ₹0.080 | 10× |
| Gemini 2.5 Flash | $0.30 / $2.50 | ₹0.125 | 6.7× |
| Claude Haiku 4.5 | $1.00 / $5.00 | ₹0.277 | 3× |
| Claude Sonnet 5 | $3.00 / $15.00 | ₹0.832 | baseline |
| *(Sonnet, no pre-filter — what SS-020 specifies today)* | | *₹1.89* | *0.44×* |

**Answer to your question: yes, use Flash-Lite — and there's a structural reason it works, not just a price reason.**

The deterministic pre-filter doesn't only cut tokens. It **changes the job the model is doing** — from *"search a 200-item wardrobe for valid combinations and reason about them"* (hard: needs a frontier model) to *"rank 5 pre-scored candidates and write a sentence about each"* (easy: a small model is genuinely sufficient). Pre-filter and Flash-Lite are **synergistic, not independent** — that's why the combined figure is 35× and not the ~6× you'd get from either alone.

Between the two Flash-Lites: **default to 2.5 Flash-Lite** (3.3× cheaper). Promote to 3.1 Flash-Lite only where eval shows 2.5 failing — most likely ethnic-wear nuance and Hindi/regional output quality.

### 2.3 Multi-provider is a capacity and availability decision, not only a cost one

Your point about RPM/TPM headroom is the one I under-weighted, and it upgrades the router from an optimisation to a **reliability requirement**:

- **Quota headroom.** Gemini and Anthropic quotas are separate pools. Two providers ≈ double the ceiling before any rate-limit engineering.
- **Failover.** SS-020's own AC demands *"graceful fallback if Claude API is down — never a hard error to the user."* With one provider that means degrading to rule-based output. **With two it means a real answer from the other vendor.** The router satisfies an existing acceptance criterion better than the design that AC was written for.
- **Quota exhaustion is a live bug class here.** `BL-076` exists precisely because a hardcoded Gemini RPM constant went stale. Config-driven, per-provider quota tracking retires that whole category.
- **Eval and A/B become free.** Comparing models is a config change, not a branch.

So the router takes **three** inputs, not one: task complexity (cost/quality), provider health and remaining quota (capacity), and user tier (product).

---

## 3. Target architecture — designed for "limitless"

### 3.1 Occasion taxonomy — data, not types

Replace the enum with a registry. Recommended column type: **`TEXT[]` of stable slugs**, not UUID FKs.

Why slugs over FKs — three concrete reasons:
1. **The AI writes these tags.** Gemini returns `"wedding_guest"`, not a UUID. Slugs survive the round-trip without a lookup on every tag.
2. **A hard FK would *reject* novel AI output.** A soft slug + alias-normalisation table *captures* it — and unrecognised tags become a signal about occasions we haven't modelled yet. That's a data-moat input, not an error.
3. **Preserves the existing GIN index pattern** and needs no join for the hot path ("filter my wardrobe by occasion").

```
occasions
  key            TEXT PRIMARY KEY        -- 'ganesh_chaturthi', 'goa_beach_trip', 'marathon'
  parent_key     TEXT REFERENCES occasions(key)   -- hierarchy: festival > navratri > garba_night
  label          TEXT
  labels_i18n    JSONB                   -- {hi, ta, mr, bn, te, ml, kn, gu, pa}
  kind           TEXT                    -- everyday|ceremony|festival|travel|sport|
                                         --   professional|social|milestone|religious
  formality      SMALLINT                -- 0–10, drives the pre-filter
  region_scope   TEXT[]                  -- ['MH','KA'] · NULL = pan-India
  culture_scope  TEXT[]                  -- NULL = universal
  styling_rules  JSONB                   -- {avoid_colors, prefer_categories, fabric_hints,
                                         --  require_footwear_formality, ...}
  date_rule      JSONB                   -- {type: fixed|lunar|floating|user_defined, ...}
  tier_gate      TEXT                    -- free|premium|atelier
  badge_color    TEXT                    -- closes BL-008 by construction
  is_active      BOOLEAN
  sort_order     INTEGER

occasion_aliases
  alias TEXT PK, occasion_key TEXT       -- normalises free-text AI output

occasion_calendar
  occasion_key, starts_on, ends_on, region, year
```

**What this unlocks immediately, with zero further schema work:**

| Your example | How it's expressed |
|---|---|
| Ganesh Chaturthi | `kind=festival`, `region_scope=['MH','KA','GA']`, `date_rule={lunar}` |
| Navratri (9 days) | `starts_on`/`ends_on` span + child occasions per night (`garba_night`) |
| Onam · Pongal · Durga Puja · Bihu | regional rows — an INSERT each |
| Year-round regional weddings | `date_rule={user_defined}` + `culture_scope`; no Nov–Feb assumption |
| International travel | `kind=travel` + child rows by climate/destination formality |
| Sports, fitness, marathon, gym, yoga | `kind=sport`, low `formality`, own category affinities |
| Corporate offsite, conference, graduation, Griha Pravesh, Godh Bharai | `kind=professional`/`milestone` |

> **The single most important structural win:** `starts_on`/`ends_on` + `parent_key` gives multi-day series as **one primitive**. Navratri's nine nights and a wedding's sangeet/mehendi/haldi/reception are the *same shape* — "N events, one crowd, no repeats." Build it once; every festival and every wedding culture in the country gets it. **This is also the highest-value premium feature in the business model.**

**`badge_color` as a column structurally closes `BL-008`** — every occasion has a colour by construction, so the "4 of 12 coloured" inconsistency cannot recur no matter how many occasions we add.

### 3.2 Runtime config — change behaviour without a deploy

Two mechanisms, deliberately separate:

| Mechanism | Owns | Why |
|---|---|---|
| **`app_config` table** (Supabase, service-role write, short-TTL cached) | Model routing table, cost budgets, quota ceilings, pre-filter thresholds, cache TTLs | Server-side, needs to be atomic and auditable. **Model choice must be a config row, not an import.** |
| **PostHog feature flags** | Paywall copy/price A/B, feature rollout, tier gating experiments | User-targeted, needs cohort logic. Also satisfies the epics doc's existing *"A/B ready: paywall copy and pricing can be remote-configured"* requirement — for free |

### 3.3 Ports to add (`CLAUDE.md` Open/Closed, extended one layer down)

| Port | Adapters | Retires |
|---|---|---|
| `IStylingProvider` *(exists)* | `GeminiStylingAdapter(model)`, `ClaudeStylingAdapter(model)`, `MockStylingAdapter` | — |
| `IOccasionResolver` **(new)** | DB-backed resolver: (date, region, culture, tier) → applicable occasions | hardcoded occasion logic |
| `IRateLimiter` **(new)** | `UpstashRateLimiter`, later `DurableObjectRateLimiter` | locks us out of the M3 migration |
| `ICostLedger` **(new)** | Postgres ledger, Redis counters | `BL-062` |

**Adapters are parameterised by model ID**, so "use Flash-Lite" vs "use Sonnet" is a config value — not a class.

### 3.4 Why assuming diligence is safe here

You asked to assume TD-01…TD-05 passed and keep them open. **The architecture is what makes that safe.** Because model choice is a config row:

- Ship with a **conservative default** (Gemini 2.5 Flash for everyday, Sonnet for high-stakes).
- Run the eval against production traffic afterwards.
- If Flash-Lite passes → flip one config row, get 5× more.
- If Flash-Lite *fails* → we already shipped on the safe default. **Nothing to rewrite.**

The cost of being wrong about the model is a config change. The cost of being wrong about the *architecture* is a rewrite. We are buying certainty exactly where it's expensive and deferring it where it's cheap.

---

## 4. Migration cost of what's already shipped

`[VERIFIED — grep counts, 2026-07-28]`

### 4.1 Blast radius

| Surface | Count | Nature |
|---|---|---|
| Migrations | 1 new forward migration | `occasion_type` → `TEXT` |
| Backend source | **5 files** | `ai/ports/interfaces.py`, `ai/adapters/gemini_vision_adapter.py`, `ai/adapters/mock_styling_adapter.py`, `adapters/interfaces.py`, `services/wardrobe_tagging_service.py` |
| Backend tests | 6 files | assertions on the enum vocabulary |
| Mobile source | **30 files** | see §4.2 for the split |
| Generated types | 1 | `mobile/types/supabase.ts` — regenerate |

### 4.2 The 30 mobile files are not 30 hard files

| Weight | Files | Work |
|---|---|---|
| **Heavy (4)** | `wardrobe.constants.ts`, `wardrobe.types.ts`, `onboarding.taxonomies.service.ts`, `Badge.tsx`/`tokens.ts` | Replace the hardcoded union with a fetched taxonomy; extend the existing onboarding taxonomy service to serve wardrobe occasions too — **merging the split brain** |
| **Medium (8)** | `wardrobe.store/selectors/queries/service`, `WardrobeFilterSheet`, `EditItemTagsForm`, `ReviewStep`, `ItemDetailSheet` | Type change + source swap |
| **Light (18)** | screens, chips, skeletons, dev-ui-kit, home constants | Mechanical — mostly a type import and a data source |

### 4.3 The migration itself is cheaper than it looks

The enum → text conversion is **lossless and mechanical**:

```sql
ALTER TABLE wardrobe_items
  ALTER COLUMN occasion_tags TYPE TEXT[] USING occasion_tags::text[];
-- same for outfits.occasion, suggestion_sessions.occasion, social_posts.occasion
DROP TYPE occasion_type;
```

All 12 existing values become `occasions` rows with identical keys. **No data is lost, no value is renamed, every existing tagged item keeps its tags.**

Three hard rules:
1. **Forward migration only (`007_…`).** Never edit `001_initial.sql` — it breaks the CI drift check and every local dev DB. (`BL-060` documents that check's false-positive history; don't feed it.)
2. **Verify the staging Supabase project before running.** The plan assumes no production data; confirm rather than assume.
3. **Ship the `occasions` table seeded and readable *before* any consumer switches to it.** Expand → migrate → contract, even at zero data — it keeps every step independently revertible.

### 4.4 Breaking-changes register

| # | Break | Affected shipped tickets | Mitigation |
|---|---|---|---|
| B1 | `occasion_type` enum removed | SS-002, SS-012, SS-013, SS-014, SS-015 | Lossless cast; keys unchanged |
| B2 | `OccasionType` TS union → runtime-fetched | SS-004, SS-005, SS-008, SS-013, SS-014, SS-015 | Type becomes `string`; **compile-time exhaustiveness is genuinely lost** — replaced by runtime validation + tests |
| B3 | `OCCASION_TYPES` constant removed | SS-013, SS-014 | Served by the taxonomy service (SS-004's existing pattern) |
| B4 | `OCCASION_BADGE_COLOR_MAP` removed | SS-008 | `badge_color` column — **closes `BL-008`** |
| B5 | Gemini tagging must emit slugs + normalise | SS-012 | `occasion_aliases` table absorbs unrecognised output |
| B6 | Onboarding + wardrobe taxonomies unify | SS-004 | Net simplification — two sources become one |

**B2 is the one real regression** and deserves an honest note: we trade compile-time exhaustiveness for runtime extensibility. That is the *correct* trade for a taxonomy that must grow without a release — but it must be paid for with **runtime validation at every write boundary plus tests**, or it becomes a silent-bug generator. This is a QA requirement, not a nice-to-have.

### 4.5 Mandatory regression scope

Every shipped ticket below has ACs that pass through occasion handling and **must be re-verified, not assumed**:

| Ticket | Re-verify |
|---|---|
| SS-004 | Onboarding Step 3 occasion priorities — selection, persistence, skip |
| SS-005 | Home occasion quick-select pills |
| SS-008 | `Badge` occasion variants across *all* occasions, not just the 4 |
| SS-012 | Gemini tagging emits valid slugs; unknown output normalises rather than fails |
| SS-013 | Upload Review step occasion chips |
| SS-014 | Catalogue occasion filter — including multi-select and empty results |
| SS-015 | Item edit — occasion tag add/remove/persist |

---

## 5. Ticket plan

### Wave 0 — Foundation *(blocks SS-020; run the two in parallel worktrees)*

| ID | Title | Risk | Arch | Dev | QA | Total |
|---|---|---|---|---|---|---|
| **SS-025** | Occasion Taxonomy & Extensibility Migration | **high** | 6h | 14h | 8h | **28h** |
| **SS-026** | Runtime Config Substrate (`app_config` + PostHog flags) | med | 3h | 8h | 3h | **14h** |

SS-025 is `Risk: high` — schema + migration + RLS + it touches seven shipped tickets. **Full lane, every gate, plus the §4.5 regression pass.** No shortcuts here; this is exactly the case `CLAUDE.md`'s risk-weighting rule exists for.

### Wave 1 — AI core *(parallel after Wave 0; three independent worktrees)*

| ID | Title | Risk | Arch | Dev | QA | Total |
|---|---|---|---|---|---|---|
| **SS-027** | Styling Rules Engine + Deterministic Pre-Filter | med | 5h | 12h | 5h | **22h** |
| **SS-028** | Multi-Provider Router + Gemini Styling Adapters | **high** | 6h | 14h | 7h | **27h** |
| **SS-029** | Cost & Capacity Ledger (paise-based limiting) | **high** | 4h | 10h | 5h | **19h** |

SS-027 is the highest-value/lowest-risk item in the whole plan: **pure, deterministic, no external dependencies, fully unit-testable**, and it independently delivers ~6× on any provider. It also makes SS-020's *"item IDs must not be hallucinated"* AC **structurally impossible to fail** rather than prompt-dependent.

⚠️ **SS-027 non-negotiable design constraint:** colour/formality/occasion rules must live in **one** `styling_rules` module consumed by *both* the pre-filter scorer and the prompt template. Two copies will drift, and drifted style rules are invisible until a user gets white suggested for a wedding. This is the single most likely long-term maintenance failure in the design.

### Wave 2 — The feature

| ID | Title | Risk | Total | Change |
|---|---|---|---|---|
| **SS-020** *(revised)* | Outfit Suggestion Endpoint | **high** | **20h** | Becomes *assembly* of SS-027/028/029, not a monolith. Architect effort drops |
| **SS-023** | Suggestion UI (Occasion Flow) | med | 6 pts | Now renders a *dynamic* occasion grid |
| **SS-021** | Style Score | med | 3 pts | `occasion_coverage` now counts against the live taxonomy, not a fixed 8 |
| **SS-022** | Weather | low | 2 pts | Unchanged |

### Wave 3 — Extensions *(the moat)*

| ID | Title | Notes |
|---|---|---|
| **SS-030** | Occasion Calendar & Proactive Engine | Regional/lunar date rules → proactive nudges. **The retention mechanism** |
| **SS-031** | Multi-Day Event Series Planner | Navratri, wedding series, festival weeks — one primitive. **Premium/Atelier anchor** |
| **SS-032** | Global Trend Clusters (Epic 6, rearchitected) | ₹463 Cr/yr → ₹21k/yr. Design before Epic 6 is transcribed |
| **SS-024** | Footwear Module | Unchanged; sequence last in Epic 3 |

### Revised critical path

```
SS-025 ─┬─> SS-027 ─┐
        │            ├─> SS-020 ─> SS-023 ─> SS-024
SS-026 ─┴─> SS-028 ─┤              │
            SS-029 ─┘              └─> SS-030 ─> SS-031
                       SS-021, SS-022 (parallel, after SS-025)
```

---

## 6. Honest cost of this plan

**Wave 0 + Wave 1 + revised SS-020 = ~130 hours (~16 working days).**

I previously told you Tier A was "~17h marginal." **That number was for the SS-020 design delta alone.** This plan is larger because you asked for something larger — the limitless-occasion foundation. I'd rather show the growth than let it hide:

| Option | Effort | Delivers |
|---|---|---|
| **A. Naive SS-020** | ~20h | Ships the feature. ₹1.89/call. Occasions stay frozen at 12. Rewrite later |
| **B. Cost fix only** *(original Tier A)* | ~55h | ₹0.024–0.125/call. Occasions still frozen |
| **C. This plan** | ~130h | ₹0.024–0.125/call **+** limitless occasions **+** config substrate **+** cost ledger **+** provider failover |

**C costs ~75h more than B and ~110h more than A.** What that buys: every festival, travel, sport, fitness and regional-wedding feature becomes an INSERT instead of a release cycle — permanently — and the multi-day-series primitive that anchors the premium tier.

**My recommendation: C, but with a checkpoint.** Do Wave 0 first (42h). It is the irreversible part and the part that gets more expensive every week. Re-decide on Wave 1 with Wave 0 actually in hand. If Wave 0 runs long, Wave 1 still degrades gracefully to option B.

---

## 7. Backlog disposition

| ID | Disposition |
|---|---|
| `BL-008` occasion colour gap (deferred 4×) | **RESOLVED by SS-025** — `badge_color` column makes it structural |
| `BL-062` no per-user cost cap | **RESOLVED by SS-029** |
| `BL-064` pattern/fabric free-text, no vocabulary | **PATTERN ESTABLISHED by SS-025** — same registry shape applies; log a follow-on |
| `BL-076` Gemini 15 RPM hardcoded | **RESOLVED by SS-028** — quota becomes config |
| `BL-034` first-suggestion reward hook | Unchanged — SS-020/SS-023 |
| `BL-037` no Railway deploy | Unchanged |
| `BL-060` CI drift-check false positives | **Elevated to a watch item** — SS-025 is a schema ticket; expect noise |

**New rows to create (11):** SS-025 scope guards (occasion validation at write boundaries; alias-normalisation coverage), `IRateLimiter`/`ICostLedger` port extraction, model-eval-after-launch (TD-01…TD-05 as a live item, since we're assuming rather than proving), TD-06 Replicate re-pricing **(Parked, per your call)**, plus BL-077…BL-087 from the consolidation proposal.

---

## 8. Risks

1. **SS-025 touches seven shipped tickets.** Highest regression risk in the plan. Mitigation: §4.5 is a mandatory, itemised QA scope — not a judgement call.
2. **B2's loss of compile-time exhaustiveness** is a real, permanent trade. Mitigation: runtime validation at every write boundary + tests, enforced in SS-025's QA.
3. **Diligence is assumed, not proven.** Mitigation: §3.4 — conservative defaults, config-driven promotion.
4. **Scope creep into a platform project.** The Wave-0 checkpoint in §6 exists precisely to catch this.
5. **Solo bandwidth.** 130h is ~3 weeks of nothing else. Real cost: Epic 3 user-visible delivery slips ~3 weeks.
6. **CI schema drift-check noise** on a schema-heavy ticket (`BL-060`).

---

## 9. Decisions I need from you

| # | Decision | Default if you don't pick |
|---|---|---|
| 1 | **Option A, B or C** (§6) | C with the Wave-0 checkpoint |
| 2 | Confirm **no production data** in any Supabase project | I verify before SS-025 runs |
| 3 | `TEXT[]` slugs vs UUID FK (§3.1) | Slugs — reasoning in §3.1 |
| 4 | Default everyday model at launch | Gemini 2.5 Flash (safe), promote to Flash-Lite post-eval |
| 5 | Cut SS-025…SS-029 raw tickets now, or after you review this? | Wait for your word |
| 6 | Does SS-030/SS-031 (calendar + series) enter Epic 3, or a new Epic 3.5? | New epic — Epic 3 is already 5 tickets |

---

## 10. Immediate next steps once approved

1. Verify no production data in the staging Supabase project *(blocking, 15 min)*
2. Write `docs/tickets/raw/SS-025.md` … `SS-029.md`
3. Append the backlog rows in §7
4. Update `docs/worklog/README.md` with the Epic 3 re-sequencing and a pointer to this doc
5. Amend `docs/tickets/raw/SS-020.md` — it currently specifies "Claude Sonnet call" over a full wardrobe context, which this plan supersedes
6. Log an entry in `docs/ARCHITECTURE_AMENDMENTS.md` — the occasion model is a genuine departure from the original HLD/LLD
7. Run SS-025 Architect (full lane, `model: opus` per the schema/migration triage rule)
