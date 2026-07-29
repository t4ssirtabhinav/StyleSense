# Technical Diligence — Platform & AI Provider Consolidation

**Status:** Diligence document for a proposal. No implementation authorised.
**Companion to:** [`PLATFORM-CONSOLIDATION.md`](PLATFORM-CONSOLIDATION.md)
**Date:** 2026-07-28

This document answers: *what must be proven before we commit, what does each move actually cost in Architect/Developer/QA effort, what breaks, and how do we get out if it goes wrong.*

---

## 0. Reading this document

Effort is expressed in the repo's own units — story points and hours per pipeline phase (`architect` → `developer` → `qa` → `devops`), and a `Risk:` field per `CLAUDE.md`'s two-lane rule (`high` = full lane, every human gate; `low`/`med` = fast lane).

Effort figures are **estimates by analogy** to shipped tickets (SS-011/SS-012 for provider integration, SS-018 for Upstash rate limiting, SS-002 for schema/RLS). They are not measured. A solo developer with Claude Code assistance is assumed — the same conditions that produced SS-010 through SS-015.

---

## Part 1 — Technical diligence required before commitment

Nothing below has been proven. Each item is a **blocking** question for its migration; a migration cannot be ticketed until its diligence items resolve. Estimated effort is investigation time, not implementation.

### AI provider diligence

| ID | Question | Method | Effort | Blocks |
|---|---|---|---|---|
| **TD-01** | Does Gemini 2.5 Flash produce acceptable Indian-fashion styling reasoning vs Claude Sonnet 5? | **Blind eval, 50 real wardrobes × 8 occasions.** Score on: valid item IDs, occasion appropriateness, ethnic-wear correctness, `wedding_guest` white-rule compliance, Hindi output quality. Two-rater where possible | 8h | A1, all AI consolidation |
| **TD-02** | Where exactly is the quality cliff? Which occasions genuinely need Sonnet? | Segment TD-01 results by occasion. Output: the routing table | 3h | A1 |
| **TD-03** | Does the pre-filter degrade suggestion quality? Does a 20-candidate deterministic pool contain the outfits a full-wardrobe LLM pass would have found? | Generate both ways for 30 wardrobes; measure overlap and rated quality | 6h | A1, A2 |
| **TD-04** | Real token counts per call — our 5,000-in/500-out estimate is unmeasured | `POST /v1/messages/count_tokens` against 20 real serialised wardrobes across sizes (10/50/100/200 items) | 2h | all cost claims |
| **TD-05** | Does Gemini grounding at ~50 global queries/day actually produce India-relevant fashion trends? | Run 7 days of global queries; manually assess relevance vs a Perplexity control | 6h | A3, Perplexity removal |
| **TD-06** | **Re-verify Replicate pricing.** ₹0.19 / ₹4.15 are inherited, unchecked, and drive ~40–50% of COGS | Read current Replicate pricing; run 10 real generations; measure billed cost | 2h | entire COGS model |

> **TD-01 is the highest-stakes item in this document.** Every financial claim in the consolidation case rests on Gemini Flash being good enough for the everyday tier. **If it isn't, the routing still works — Claude Haiku 4.5 + pre-filter at ₹0.28/call is the fallback**, still 6.75× better than SS-020's current spec. The architecture survives a negative TD-01; only the magnitude changes.

### Infrastructure diligence

| ID | Question | Method | Effort | Blocks |
|---|---|---|---|---|
| **TD-07** | Are Python Workers / Cloudflare Containers production-ready for a FastAPI app? | Read current CF docs; deploy a spike | 4h | C2 *(expected: no — keep Railway)* |
| **TD-08** | Do Durable Objects give us correct atomic rate limiting under concurrency? | Spike: 1,000 concurrent requests against one user's limit; assert exactly N pass. **Run the same test against current Upstash to quantify the delta** | 6h | B2 |
| **TD-09** | Does a DO round-trip from Railway (likely India/Singapore region) meet SS-020's `<200ms cache hit` AC? | Latency benchmark, p50/p95/p99, from the actual backend region | 3h | B2 |
| **TD-10** | pgvector performance at 1M+ item embeddings on Supabase's plan — and which embedding model/dimensions? | Load-test with synthetic vectors at 100k/1M/5M; check HNSW build time and memory | 6h | B1 |
| **TD-11** | Does PostHog error tracking symbolicate React Native **native** crashes (Hermes stack traces, iOS dSYM, Android mapping)? | Force a native crash in a release build; verify the trace is readable | 4h | B4 *(expected: no — keep Sentry on mobile)* |
| **TD-12** | Do PostHog's free tiers genuinely stack, or is there a combined plan minimum? | Read pricing terms; confirm with support in writing | 1h | B4, B7 |
| **TD-13** | MSG91 email deliverability vs Resend for transactional mail to Indian inboxes | 100-send test across Gmail/Outlook/Yahoo; measure inbox vs spam | 4h | C3 |
| **TD-14** | Can pg_cron reliably trigger a Railway-hosted FastAPI endpoint (via pg_net) with retries and failure visibility? | Spike: scheduled call + induced failure + alerting path | 4h | B3 |
| **TD-15** | Supabase egress and compute cost curve at 100k / 1M MAU — the "it's cheap" assumption is unverified | Model from current published pricing against projected read/write/egress volume | 3h | all scale claims |
| **TD-16** | Does Turnstile work inside an Expo React Native client, or is it web-only? | Spike on the actual RN client | 4h | B6 |

**Total diligence: ~66 hours (~8–9 working days).** This is deliberately front-loaded — every hour here prevents a multi-week migration built on a false assumption.

---

## Part 2 — Per-migration effort, risk and strategy

### M1 — Provider routing + pre-filter + cross-user cache *(Tier A: A1, A2)*

The whole financial case. **This is not a migration — it is a design decision inside SS-020, which has not been implemented.**

| Phase | Effort | Work |
|---|---|---|
| Architect | 6h | Routing table from TD-02; pre-filter scoring algorithm; combination-signature cache-key spec; `GeminiStylingAdapter` conforming to the *existing* `IStylingProvider`; fallback chain |
| Developer | 14h | Pre-filter scorer (deterministic, pure, unit-testable); `GeminiStylingAdapter`; router; cache-key builder; cost-logging fields; full test suite |
| QA | 6h | AC verification incl. the `<4s` cold call and `<200ms` cache hit against a **real non-trivial wardrobe** per SS-020's own edge-case note; boundary sweep on the free-tier gate |
| **Total** | **26h (~5 pts)** | vs ~8h for the naive Sonnet-over-full-wardrobe version |

**Risk: `high`** — full lane. Touches the free-tier revenue gate and the flagship user-facing feature.

**Net cost of doing it right: ~18 extra hours.** Against a permanent 8–15× reduction in the unit cost of the product's core action. This is the best-value 18 hours available anywhere in the backlog.

**Risks & limitations**
- *Quality regression on ethnic wear.* Gemini Flash may miss saree/lehenga nuance that Claude handles. **Mitigation:** TD-01 gates this; routing sends all ethnic + high-stakes occasions to Sonnet regardless of TD-01's outcome.
- *Pre-filter becomes a second source of truth for style rules.* Colour/formality logic now lives in Python **and** in the prompt; they can drift. **Mitigation:** single `styling_rules.py` module consumed by both the scorer and the prompt template. Non-negotiable — this is the most likely long-term maintenance failure in the design.
- *Cross-user cache leaks personalisation.* Two users with the same combination signature get identical reasoning. Acceptable for generic items; **wrong if reasoning references user name, city, or `style_preferences`.* **Mitigation:** cache the *outfit + rationale skeleton*; render personalisation client-side or in a cheap post-pass.
- *Cross-user cache is a privacy surface.* A cache key derived from item attributes must not be reversible into another user's wardrobe. **Mitigation:** salted hash; store no `user_id` in the shared cache entry. **Explicit QA boundary-sweep item.**

**Migration strategy:** none needed — nothing to migrate. Build it right the first time.

---

### M2 — Global trend clusters *(Tier A: A3)*

| Phase | Effort | Work |
|---|---|---|
| Architect | 5h | Global cluster job design; cluster→wardrobe matching via pgvector; activity gating (7-day active only); scheduling |
| Developer | 12h | Grounded-query job; cluster storage schema; embedding + match; per-user materialisation |
| QA | 4h | Relevance spot-check; verify **zero per-user LLM calls**; dormant users cost nothing |
| **Total** | **21h (~4 pts)** | |

**Risk: `med`** — no revenue gate, no PII, but a cost-shaped design decision.

**Why now:** Epic 6 has no tickets. Designing it per-user then rewriting it costs ~3× this.

**Risks & limitations**
- *Less personalised than per-user research.* Genuinely true. **Counter:** personalisation comes from the wardrobe-gap match, which is per-user and cheap; the *trend discovery* half has no reason to be per-user. Nobody's trending-fashion answer is unique to them.
- *Cluster staleness during fast-moving moments* (festival drops, celebrity events). **Mitigation:** increase cadence seasonally — cost is flat per query, so this is affordable.
- *Depends on pgvector (B1) landing first.* Hard sequencing dependency.

---

### M3 — Upstash → Cloudflare Durable Objects *(Tier B: B2)*

| Phase | Effort | Work |
|---|---|---|
| Architect | 4h | DO class design (per-user counter, TTL/reset semantics, fail-closed behaviour); dual-write cutover plan |
| Developer | 10h | DO Worker; backend client; feature-flagged swap; parity tests |
| QA | 6h | **Concurrency correctness is the entire point** — 1,000-concurrent boundary test; fail-closed verification when the DO is unreachable; latency against SS-020's `<200ms` AC |
| **Total** | **20h (~4 pts)** | |

**Risk: `high`** — this is the free-tier revenue gate. `CLAUDE.md`'s boundary sweep (empty/max/duplicate/concurrent/stale) is mandatory.

**Risks & limitations**
- *Adds a network hop* Railway → Cloudflare on every gated request. TD-09 must clear this before commitment. **If p95 exceeds ~50ms, do not migrate** — the AC matters more than the vendor count.
- *Fail-closed on DO unreachability locks out paying users.* Current Upstash pattern has the same property, so this is not a regression — but at DO's different failure profile it deserves a re-decision. **Mitigation:** fail-closed for free tier, fail-*open* with logging for verified premium. Premium users must never be locked out of a feature they paid for by an infra blip.
- *Worker language boundary.* Rate-limit logic moves from Python to JS/TS — a second language for a solo team, and a place for logic to drift.

**Migration strategy — dual-write, shadow-read:**
1. Deploy DO alongside Upstash. Write both, read Upstash. Log disagreements.
2. Run ≥7 days. **Zero unexplained disagreements is the gate.**
3. Flip reads to DO, keep writing both, keep Upstash as instant rollback.
4. After 14 clean days, drop Upstash.

**Rollback:** single feature flag through step 3. Under 5 minutes.

---

### M4 — pgvector adoption *(Tier B: B1)*

| Phase | Effort | Work |
|---|---|---|
| Architect | 4h | Embedding model + dimension choice; index strategy (HNSW params); migration + RLS on the embedding table |
| Developer | 10h | Migration; embedding generation on item create/update; backfill; similarity query layer |
| QA | 4h | Recall quality; index performance at volume; **RLS correctness on embeddings** — a vector table is a new data-exfiltration surface |
| **Total** | **18h (~3 pts)** | |

**Risk: `high`** — schema + migration + RLS. Full lane, non-negotiable per `CLAUDE.md`.

**Risks & limitations**
- *Embedding-model lock-in.* Changing models later means re-embedding everything. **Mitigation:** store `embedding_model` and `embedding_version` columns from day one; support two live indexes during any future swap. Cheap now, very expensive to retrofit.
- *Index rebuild time at millions of rows* can mean extended locks. **Mitigation:** `CREATE INDEX CONCURRENTLY`; verify against Supabase's timeout limits (TD-10).
- *pgvector competes with OLTP for the same Postgres resources.* At scale, similarity search can degrade normal queries. **Mitigation:** read replica when it bites; this is a known escape hatch, not a surprise.

**Migration strategy:** additive-only. New table, new column, backfill in batches, feature-flagged reads. No destructive step. Rollback = drop the index and disable the flag.

---

### M5 — Sentry-backend → PostHog error tracking *(Tier B: B4)*

| Phase | Effort |
|---|---|
| Architect | 2h |
| Developer | 5h |
| QA | 2h |
| **Total** | **9h (~2 pts)** |

**Risk: `low`** — fast lane. Observability-only, no user-facing surface.

**Limitations:** alerting maturity and integration ecosystem are weaker than Sentry's. **Mobile stays on Sentry** pending TD-11 (expected outcome: it stays permanently).

**Migration strategy:** run both for 30 days, compare captured-exception counts, then remove Sentry from the backend only. **Never remove the incumbent before a full comparison window** — the failure mode is discovering your error tracking has been silently broken during an incident.

---

### M6 — Vercel → Cloudflare Pages *(Tier B: B5)*

| Phase | Effort |
|---|---|
| Architect | 1h · Developer | 4h · QA | 2h |
| **Total** | **7h (~1 pt)** |

**Risk: `low`.** **Do this opportunistically during another web-touching ticket. Never as its own project** — the standalone value doesn't justify a ticket's overhead.

**Limitation:** Vercel's preview-deploy-per-PR is currently wired into CI (`ci.yml` has Vercel checks). Pages has an equivalent, but it is a CI change, and CI changes on a repo with a documented drift-check history (`BL-060`) carry more risk than the migration itself.

---

### M7 — Turnstile + WAF on auth endpoints *(Tier B: B6)*

| Phase | Effort |
|---|---|
| Architect | 3h · Developer | 8h · QA | 4h |
| **Total** | **15h (~3 pts)** |

**Risk: `high`** — auth-adjacent. Full lane.

**This is the only item here that is a security gap rather than an optimisation.** The OTP endpoint currently has no bot protection. SMS-pumping (attacker triggers mass OTP sends to premium-rate numbers, splits the carrier revenue) is a live, common, automated attack against Indian phone-auth apps. It costs real money on the first night and there is no recovery.

**Limitations:** TD-16 must confirm Turnstile works in an Expo RN client. If it doesn't, fall back to device attestation (Play Integrity / App Attest) + aggressive per-IP/per-device edge limits. **The mitigation changes; the requirement does not.**

**Migration strategy:** monitor-only mode first (log what *would* be blocked), tune thresholds against real traffic, then enforce. Never enforce a new bot rule blind on an auth path.

---

## Part 3 — Effort summary

| Migration | Tier | Arch | Dev | QA | Total | Risk |
|---|---|---|---|---|---|---|
| M1 Provider routing + pre-filter + cache | A | 6h | 14h | 6h | **26h** | high |
| M2 Global trend clusters | A | 5h | 12h | 4h | **21h** | med |
| M3 Upstash → Durable Objects | B | 4h | 10h | 6h | **20h** | high |
| M4 pgvector | B | 4h | 10h | 4h | **18h** | high |
| M5 Sentry-backend → PostHog | B | 2h | 5h | 2h | **9h** | low |
| M6 Vercel → CF Pages | B | 1h | 4h | 2h | **7h** | low |
| M7 Turnstile + WAF | B | 3h | 8h | 4h | **15h** | high |
| | | **25h** | **63h** | **28h** | **116h** | |
| Diligence (Part 1) | — | — | — | — | **66h** | |
| **Grand total** | | | | | **~182h (~23 working days)** | |

**But that total is misleading, and reading it as a project plan would be the wrong conclusion.**

- **Tier A (M1 + M2 = 47h) is not migration work.** It is the *correct* version of tickets we are about to write anyway. The naive versions cost ~30h. **True marginal cost of Tier A: ~17 hours.**
- **Tier B (69h) is spread across months**, attached to tickets that would otherwise force the bad version.
- **Diligence (66h) is mostly TD-01 through TD-06 (27h)**, which gates Tier A and should happen regardless — we cannot responsibly pick a model for the flagship feature without an eval.

**Honest framing: ~44 hours (17h implementation + 27h AI diligence) buys the entire financial case. The remaining ~138h is optional, deferrable, and trigger-driven.**

---

## Part 4 — Cross-cutting risks

### R1 — Concentration and blast radius
Nine vendors means each is more load-bearing. Cloudflare failing would take storage + counters + queues + bot protection + web hosting at once.
**Mitigation:** extend the ports/adapters discipline from AI to infra. `IRateLimiter`, `IObjectStore`, `IJobQueue` as ABCs in `backend/ai/ports/`-style modules, with the concrete vendor behind them. This is the *same* Open/Closed rule `CLAUDE.md` already mandates for AI providers, applied one layer down. It converts "we are locked into Cloudflare" into "we have a Cloudflare adapter."

### R2 — Cost model built on one unverified number
`₹4.15/try-on` drives ~40–50% of projected AI COGS and has never been checked (TD-06). Everything downstream — per-MAU cost, gross margin, the Y5 EBITDA line, the investor deck — inherits that uncertainty.
**Mitigation:** TD-06 is 2 hours. Do it before any external financial claim is made.

### R3 — Solo-team migration bandwidth
Every hour here is an hour not shipping Epic 3. Consolidation produces zero user-visible value.
**Mitigation:** the trigger-based sequencing exists precisely for this. Only Tier A is time-sensitive, and only because the code isn't written yet.

### R4 — Two languages, one team
Durable Objects (JS/TS) + Edge Functions (Deno) + FastAPI (Python) + Expo (TS) is four runtimes for one person.
**Mitigation:** keep DO logic *minimal* — a counter and a TTL, nothing more. Any business logic in a Worker is a mistake. If a DO needs branching, it belongs in Python.

### R5 — Verification decay
This document verified four vendors' pricing on 2026-07-28. Anthropic's Sonnet intro rate **expires 2026-08-31**. Cloud pricing moves quarterly.
**Mitigation:** treat every number here as expiring. Re-verify at each Tier-B trigger. **Do not carry these figures into a document dated more than a quarter from now without re-checking** — that is exactly how `₹4.15` became load-bearing without anyone noticing.

### R6 — The migrations that touch money are the ones most likely to break quietly
M1 (revenue gate + flagship feature) and M3 (revenue gate) can both fail *silently* — a rate limiter that lets 4 calls through instead of 3, or a router that quietly sends everything to the expensive model. Neither throws an error.
**Mitigation:** both ship with **assertions in production, not just tests** — a counter that logs every time a limit is exceeded by even one, and a per-request cost log (`user_id`, `provider`, `model`, `tokens`, `paise`) that makes routing drift visible on a dashboard within a day. `CLAUDE.md` already requires the AI-call log; this extends it with the routing decision and cost.

---

## Part 5 — Longevity: what makes this survive five years

The consolidation is worth little if it has to be redone. Four properties to preserve:

1. **Every external dependency sits behind a port.** Already true for AI. Extend to rate limiting, object storage, and job queues (R1). This is what makes any future vendor change a two-week adapter swap instead of a quarter.

2. **Cost is a first-class observable, not an invoice surprise.** Per-request `paise` logging (R6), a per-user cost ledger, and a dashboard. You cannot control what you only see 30 days later on a bill.

3. **Model choice is configuration, not code.** The routing table lives in config with a feature flag, so moving from Gemini 2.5 Flash to whatever is cheapest in 2028 is a config change and an eval — not a ticket. **This is the mechanism that makes the business plan's "we ride the AI cost curve down" claim actually true instead of aspirational.**

4. **Architecture beats vendor selection, every time.** The pre-filter saves 6× on any provider. Global clustering saves O(users) on any provider. Cross-user caching saves ~50% on any provider. Those three compound to ~12× and survive every vendor change, price rise and model deprecation ahead of us. **Vendor choice is the last 2–8×, and the only part that can be taken away from us.**

---

## Part 6 — Open questions requiring a human decision

1. **Is a quality drop on everyday suggestions acceptable for an 8× cost reduction?** TD-01 produces the data; the trade is a product call, not a technical one.
2. **Should premium users always get the quality tier**, regardless of occasion? Simple, defensible, and makes ₹149 mean something concrete — but raises premium COGS at exactly the tier that already struggles to cover it (see the business doc).
3. **Is fail-open acceptable for premium rate limits?** Locking out a paying user on an infra blip vs. absorbing a small amount of abuse.
4. **Do we ever want to run our own inference?** Try-on economics say yes eventually. That is a hiring decision, not an architecture decision, and it should be made deliberately rather than arrived at.
