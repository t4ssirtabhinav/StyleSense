# Proposal — Platform & AI Provider Consolidation

**Status:** Proposal only. Not approved, not scheduled, no tickets cut.
**Author:** Architect pass, 2026-07-28
**Companion docs:** [`PLATFORM-CONSOLIDATION-TECHNICAL.md`](PLATFORM-CONSOLIDATION-TECHNICAL.md) (diligence + effort + migration) · [`PLATFORM-CONSOLIDATION-BUSINESS.md`](PLATFORM-CONSOLIDATION-BUSINESS.md) (business/investor case)

---

## Provenance of every number in this document

Per `CLAUDE.md` §Process Discipline ("Verify, don't recite" / "Label known vs. guessed"):

| Claim class | Status |
|---|---|
| Anthropic model pricing | `[VERIFIED 2026-07-28]` — `claude-api` skill pricing table |
| Google Gemini model + image + grounding pricing | `[VERIFIED 2026-07-28]` — `ai.google.dev/gemini-api/docs/pricing` |
| Cloudflare Workers / Durable Objects / KV / Queues pricing | `[VERIFIED 2026-07-28]` — `developers.cloudflare.com/workers/platform/pricing/` |
| PostHog per-product pricing + free tiers | `[VERIFIED 2026-07-28]` — `posthog.com/pricing` |
| Replicate per-action costs (₹0.19 BG removal, ₹4.15 try-on) | **UNVERIFIED** — carried from `init documents/`; inherited assumption, not checked |
| Supabase / Railway / Upstash / MSG91 / Razorpay pricing | **UNVERIFIED** — directional only |
| Token counts per call (e.g. "~5,000 input tokens") | **ESTIMATE** — no `ClaudeStylingAdapter` exists yet to measure |
| INR conversion at ≈₹84/$1 | **APPROXIMATE** — not checked against a live rate |
| Every platform *capability* claim (e.g. "Durable Objects give atomic counters") | **INFERENCE** from documentation reading — each carries a diligence item in the technical doc |

Nothing in this document should be treated as verified unless the row above says so.

---

## 1. The problem

We run **15 external vendors**, and almost every one is used for a single slice of what it does:

| Vendor | What we use it for | What it also does that we pay someone else for |
|---|---|---|
| Cloudflare | R2 object storage, only | Compute, atomic counters, image transforms, bot protection, queues, static hosting, WAF |
| Supabase | Postgres + Auth + RLS | Vector search, cron, queues, realtime, storage, edge compute |
| Upstash | Redis counters for rate limits | (nothing else we need) |
| PostHog | Product analytics | Error tracking, feature flags, A/B, session replay, surveys |
| Sentry | Error tracking | (overlaps PostHog) |
| Gemini | Vision tagging, only | Text reasoning, image generation, search grounding |
| Anthropic | Styling reasoning | Vision |
| Perplexity | Trend search | (overlaps Gemini grounding) |
| Replicate | BG removal + avatar + try-on | (specialist — genuinely hard to replace wholesale) |
| Railway | FastAPI hosting | — |
| Vercel | Web hosting | (overlaps Cloudflare Pages) |
| Razorpay, MSG91, Resend, Expo EAS | Payments, SMS, email, builds | — |

Three costs compound with every vendor, and only one of them is the invoice:

1. **Money** — per-vendor minimums, and per-vendor free tiers we exhaust in parallel instead of pooling.
2. **Integration surface** — 15 sets of credentials, SDKs, failure modes, rate limits, status pages, and version churn. Every one is a thing that can break the app at 2am and a thing a solo team has to keep current.
3. **Cognitive load** — the real tax. `BL-076` exists because a Gemini rate-limit constant went stale when an account tier changed. That class of drift scales linearly with vendor count.

---

## 2. What consolidation is *not*

Three honest constraints, stated up front so this proposal doesn't read as a cost fantasy:

**Consolidation is not automatically cheaper.** Two of the moves I expected to be big wins turned out not to be, once I pulled real prices (§4). Specialist vendors are often specialist *because* they're cheap at their one thing.

**At today's scale this proposal saves ₹0.** We have no production users. Everything is on free tiers. Executing this now costs weeks and saves nothing. **The value is entirely in avoiding a rewrite later** — and in a small number of moves that are worth doing early *because they are architectural, not operational* (§6).

**Vendor count is not the goal.** Going from 15 to 9 vendors while making the app slower, less observable, or harder to debug is a net loss. The goal is: fewest vendors that still lets us build everything in Epics 3–8 without a future forced migration.

---

## 3. The verified findings that changed my recommendations

I went in with five hypotheses. Real pricing killed two of them and upgraded a third.

### ❌ Killed: "Move image generation to Gemini and drop Replicate"

`[VERIFIED 2026-07-28]`

| Action | Current (Replicate, *unverified*) | Gemini equivalent (verified) | Verdict |
|---|---|---|---|
| BG removal | ~₹0.19 | Gemini 2.5 Flash Image, ₹3.28/image | **17× worse.** Never move this |
| Avatar / try-on | ~₹4.15 | Gemini 2.5 Flash Image, ₹3.28/image | ~21% cheaper — marginal |
| Try-on (higher fidelity) | — | Gemini 3.1 Flash Image, ₹5.63/image | **36% worse** |

Moving try-on to Gemini saves ~₹0.87/generation and removes a vendor. That is *not* the order-of-magnitude win the COGS problem needs. **The real answer for try-on remains dedicated/self-hosted inference**, which is an infrastructure investment, not a vendor swap. Do not sell this as a consolidation win.

### ❌ Killed: "Replace Perplexity with Gemini search grounding"

`[VERIFIED 2026-07-28]` Gemini 3 grounding: 5,000 prompts/month free, then **$14 per 1,000 queries ≈ ₹1.18/query**. Gemini 2.5: $35/1,000 ≈ ₹2.94/query.

Per-query, that is *more expensive* than what the planning docs assume Perplexity costs. Consolidating here on a **per-user** trend query would raise costs.

**But it flips completely under the right architecture.** Under the global-trend-cluster design (§5 of the cost analysis — compute trends once globally, match locally), you run ~50 grounded queries/day for the *entire user base*: ≈₹59/day ≈ **₹1,770/month flat, at any MAU**. Perplexity then has nothing left to do.

> The lesson generalises and is the most important sentence in this document: **the architecture decides the bill far more than the vendor does.** A per-user call is expensive on every vendor; a global call is cheap on all of them.

### ⬆️ Upgraded: "Gemini can take the volume tier of text reasoning"

`[VERIFIED 2026-07-28]` — cost per outfit-suggestion call, at our estimated 5,000 input / 500 output tokens:

| Model | $/call | ₹/call |
|---|---|---|
| Claude Opus 5 | $0.0375 | ₹3.15 |
| Claude Sonnet 5 | $0.0225 | ₹1.89 |
| Gemini 3.5 Flash | $0.0120 | ₹1.01 |
| Claude Haiku 4.5 | $0.0075 | ₹0.63 |
| **Gemini 2.5 Flash** | **$0.00275** | **₹0.23** |
| Gemini 2.5 Flash-Lite | $0.0007 | ₹0.06 |

Gemini 2.5 Flash is **8× cheaper than Claude Sonnet 5** and **2.7× cheaper than Claude Haiku 4.5** for the same call — from a vendor already in the stack for vision tagging.

Now combine with the deterministic pre-filter (send 5 pre-scored candidates to rank, not the whole wardrobe to search — input drops to ~800 tokens):

| Config | ₹/call |
|---|---|
| Claude Sonnet 5, no pre-filter (**what SS-020 currently specifies**) | ₹1.89 |
| Claude Sonnet 5 + pre-filter | ₹0.83 |
| Claude Haiku 4.5 + pre-filter | ₹0.28 |
| **Gemini 2.5 Flash + pre-filter** | **₹0.125** |
| **Blended: 85% Gemini Flash / 15% Sonnet for high-stakes occasions** | **₹0.23** |

**The business plan's ₹0.30/outfit-suggest assumption is achievable after all — just never on Claude Sonnet.** It needs the pre-filter plus a cheap volume model. That is a design decision in SS-020, which has not been implemented yet. **This is the cheapest moment in the project's life to make it.**

---

## 4. Proposed target architecture

From **15 vendors → 9**, with capability *gained*, not lost.

### Anchor 1 — Cloudflare (from 1 job to 7)

| Absorbs | Replaces | Verified cost at ~1.3M MAU scale |
|---|---|---|
| R2 object storage *(already ours)* | — | zero egress — the reason to keep it |
| **Durable Objects** — atomic rate-limit counters | **Upstash Redis** | ~26M req/mo ≈ **$3.90/mo** |
| **Workers/Queues** — background jobs | in-process FastAPI background tasks | 1M ops/mo free, then $0.40/M |
| **Turnstile** — bot protection on the OTP endpoint | *nothing today — this is an open hole* | free |
| **WAF / edge rate limiting** | *nothing today* | included |
| **Images** — resize/variants/delivery | ad-hoc client work | usage-based |
| **Pages** — Expo web export hosting | **Vercel** | free tier |

Base cost: **$5/month** covering Workers, KV, Durable Objects, Queues and Pages together.

**Durable Objects are the technically-correct primitive for rate limiting, not merely the cheaper one.** Each DO is single-threaded and strongly consistent per key, so a per-user counter cannot race. Our current Upstash pattern is fail-closed (good) but distributed-counter semantics are the classic source of "free user got 4 calls instead of 3" bugs — which is a *revenue* bug on the free-tier gate SS-020 is about to introduce.

⚠️ **Explicitly NOT proposed:** moving the FastAPI backend to Cloudflare. Python Workers maturity is unconfirmed and our backend is FastAPI-native. Railway stays. (Diligence item TD-07.)

### Anchor 2 — Supabase (from 3 jobs to 8)

| Absorbs | Replaces / prevents | Why |
|---|---|---|
| Postgres + Auth + RLS *(already ours)* | — | — |
| **pgvector** | a future Pinecone/Weaviate contract | Needed for Epic 7 "find similar" visual search **and** for the local trend-matching that makes the global-cluster design work. Adding it now prevents a vendor later |
| **pg_cron + pg_net** | an external scheduler | Nightly trending-picks, weekly reports, Style Score recompute |
| **pgmq / Queues** | in-process background tasks | Survives redeploys — current background tasks do not |
| **Realtime** | polling in the Epic 5 social feed | Already paid for |
| Edge Functions | *(already planned for payments/Style Score)* | — |

⚠️ **Explicitly NOT proposed:** moving image storage from R2 to Supabase Storage. **This would raise costs.** R2's zero egress is the single best economic property in the stack for an image-heavy app; Supabase Storage bills egress. Consolidating here is a textbook example of vendor-count-as-goal producing a worse outcome.

### Anchor 3 — AI providers (from 4 to 3, restructured by *role* not by task)

The current split is by **task** (Gemini=vision, Claude=text, Perplexity=search, Replicate=pixels). The proposed split is by **cost/quality role**:

| Role | Provider | Handles |
|---|---|---|
| **Volume workhorse** | **Gemini 2.5 Flash / Flash-Lite** | Vision tagging, ~85% of everyday outfit suggestions, gap analysis, trend matching, weekly reports |
| **Quality tier** | **Claude Sonnet 5** | High-stakes occasions (`wedding_guest`, festivals), first-ever suggestion, wedding-series planning, anything a paying user sees as the headline feature |
| **Global research** | **Gemini 3 grounding** | Trend discovery — run ~50×/day globally, not per user |
| **Pixels** | **Replicate** | BG removal (₹0.19 — nobody beats this), avatar, try-on |
| ~~Perplexity~~ | **eliminated** | absorbed by Gemini grounding under the global design |

This keeps the hexagonal contract intact: `IStylingProvider` gains a `GeminiStylingAdapter` alongside `ClaudeStylingAdapter`, and a thin router picks between them. **Per `CLAUDE.md`'s Open/Closed rule, the port does not change** — this is exactly the swap-in case the architecture was built for. It is the first real proof that the ports abstraction pays for itself.

### Anchor 4 — PostHog (from 1 job to 5)

`[VERIFIED 2026-07-28]` free tiers: 1M events, 100K exceptions, 1M flag requests, 5K replays, 1.5K survey responses — **per month, and they stack**.

| Absorbs | Replaces / prevents |
|---|---|
| Product analytics *(already ours)* | — |
| **Error tracking** | **Sentry backend** |
| **Feature flags** | a future LaunchDarkly — and the epics doc *already requires* "A/B ready: paywall copy and pricing can be remote-configured" |
| **A/B testing** | ditto — paywall price testing is a Sprint-5 requirement |
| **Session replay** | manual funnel debugging |
| **Surveys** | a future Typeform for churn/NPS |

⚠️ **Keep Sentry on mobile.** React Native **native crash symbolication** is Sentry's genuine specialism and PostHog's error tracking is not a proven equivalent there (diligence item TD-11). Proposed: **PostHog for backend errors + all product surfaces; Sentry retained for the mobile client only.** This is a partial consolidation, honestly scoped — one vendor eliminated (Sentry backend usage), one retained for a real reason.

### Final vendor list — 9

| Kept | Role |
|---|---|
| Supabase | Data, auth, vectors, cron, queues, realtime |
| Cloudflare | Storage, edge compute, counters, queues, bot/WAF, web hosting |
| Gemini | Volume AI — vision, text, grounding |
| Anthropic | Quality-tier AI |
| Replicate | Image generation |
| PostHog | Analytics, errors, flags, A/B, replay, surveys |
| Railway | FastAPI backend |
| Razorpay | Payments |
| MSG91 | SMS/OTP |
| *(Sentry — mobile crash only)* | narrowed, not removed |

**Eliminated: Upstash, Perplexity, Vercel, Resend¹, Sentry-backend.**

*¹ Resend → MSG91 email is proposed only if MSG91's deliverability holds up (TD-13). It is a ₹-trivial move; if diligence is unconvincing, keep Resend and finish at 10 vendors. Not worth fighting over.*

---

## 5. What this actually saves

Honest accounting, because the vendor-count reduction and the money are largely **different** things:

| Move | Money saved | Real reason to do it |
|---|---|---|
| Gemini volume tier + pre-filter for suggestions | **₹1.89 → ₹0.23/call (8×)** | Money. This is the whole financial case |
| Global trend clusters (Gemini grounding) | O(users) → **flat ₹1,770/mo** | Money — and it *grows* with scale |
| Upstash → Durable Objects | ~$10–50/mo | **Correctness.** Atomic counters on a revenue gate |
| Sentry-backend → PostHog | ~$300–600/yr | Vendor count, unified funnels |
| Vercel → Cloudflare Pages | ~$0–240/yr | Vendor count, one bill |
| Perplexity → Gemini grounding | small | Vendor count |
| pgvector adopted now | ₹0 today | **Prevents a vendor + migration later** |
| PostHog flags/A-B | prevents a LaunchDarkly contract | Satisfies an existing Sprint-5 requirement for free |
| Try-on → Gemini image | ~₹0.87/gen (21%) | **Marginal. Do not prioritise** |
| BG removal → Gemini image | **−₹3.09/image (17× worse)** | **Do not do this** |

**The single biggest lever in this entire document is not a vendor change.** It is the pre-filter-then-rank redesign inside SS-020, which cuts input tokens 5–10× on *whichever* provider we use. Vendor choice is a 2–8× multiplier on top of an architectural 6× — and the architectural one is free and permanent.

---

## 6. Sequencing — by trigger, not by date

Nothing here is urgent. But **three items are cheap now and expensive later**, because they change code that has not been written yet:

### Tier A — Do before the relevant ticket ships (cost: near-zero; cost of deferring: a rewrite)

| # | Move | Trigger | Why now |
|---|---|---|---|
| A1 | **Provider routing + pre-filter in SS-020's design** | Before SS-020 Architect phase | The adapter doesn't exist yet. Retrofitting a router into a shipped endpoint is 4× the work |
| A2 | **Cross-user cache key** (combination signature, not `user_id`) | Before SS-020 Architect phase | Cache keys are near-impossible to change once a populated cache is live |
| A3 | **Global trend clusters, not per-user cron** | Before Epic 6 is transcribed | Epic 6 has no tickets yet. Free to design correctly; a per-user cron is a rewrite |

### Tier B — Do at a scale trigger (cost: real; value: real)

| # | Move | Trigger |
|---|---|---|
| B1 | pgvector enabled | First ticket needing similarity search (Epic 7 visual search, or A3's trend matching) |
| B2 | Upstash → Durable Objects | First multi-instance backend deploy — the moment the in-process limiter caveat in `BL-037` becomes real |
| B3 | pg_cron / pgmq for scheduled + background work | First production cron, or first time a redeploy drops an in-flight background task |
| B4 | Sentry-backend → PostHog errors | At Sentry paid-tier crossover |
| B5 | Vercel → Cloudflare Pages | Next web deploy touch — do it opportunistically, never as its own project |
| B6 | Cloudflare Turnstile + WAF on auth endpoints | **Before public launch.** SMS-pumping fraud is not theoretical |
| B7 | PostHog event sampling policy | Before crossing 1M events/month |

### Tier C — Evaluate, probably don't do

| # | Move | Why it's parked |
|---|---|---|
| C1 | Try-on → Gemini image | Only 21% cheaper. Revisit only if bundled with a quality/latency win |
| C2 | Backend → Cloudflare Containers | Railway works. Python-on-Workers maturity unconfirmed |
| C3 | Resend → MSG91 email | Trivial money, real deliverability risk |
| C4 | **R2 → Supabase Storage** | **Actively harmful.** Listed so nobody proposes it again |

---

## 7. Risks of consolidating at all

Stated plainly, because a proposal that only lists upside isn't diligence:

1. **Concentration risk.** Nine vendors instead of fifteen means each remaining one is more load-bearing. A Cloudflare outage would take storage, counters, queues, bot protection and web hosting simultaneously — today it takes storage only. **Blast radius grows as vendor count shrinks.** Mitigation: the ports/adapters pattern already isolates AI; the technical doc specifies the same discipline for infra (TD-14).

2. **Pricing power shifts to them.** A vendor doing seven jobs can raise prices knowing migration is now a quarter of work, not a week.

3. **Free tiers stop stacking.** Part of today's ₹0 bill comes from exhausting many small free tiers in parallel. Pooling onto fewer vendors means crossing paid thresholds sooner — even at identical usage.

4. **Multi-product vendors are worse at each product.** PostHog error tracking is not Sentry. Gemini Flash is not Sonnet on nuanced reasoning. Every consolidation trades a little quality for a lot of simplicity, and the trade is only correct where quality genuinely isn't the differentiator.

5. **Migration risk is concentrated in the money paths.** The two moves touching revenue — rate limiting (free-tier gate) and provider routing (what a paying user sees) — are exactly the ones `CLAUDE.md` §Risk-weighting says to spend disproportionate effort on. Both are `Risk: high`, full-lane tickets.

---

## 8. Recommendation

**Approve Tier A now, as design changes to tickets that have not been written yet.** Three items, near-zero cost, and they are the difference between the business plan's ₹0.30/call assumption being real or fictional.

**Defer Tier B to its triggers.** Do not run a consolidation project. Attach each move to the ticket that would otherwise force the bad version of it.

**Reject C4 permanently** and treat C1–C3 as parked.

If only one thing is taken from this document: **SS-020 currently specifies a Claude Sonnet call over a full wardrobe context. That single design line is an 8–15× cost multiplier versus the alternative, on the endpoint that defines the product.** It has not been built. Change it before it is.

---

## 9. Backlog items this proposal should create

*(Not created yet — pending approval, per the "proposal only" status.)*

| Proposed | Tier | Summary |
|---|---|---|
| BL-077 | Active | SS-020: provider routing (Gemini volume / Claude quality) behind `IStylingProvider` |
| BL-078 | Active | SS-020: deterministic pre-filter-then-rank; also structurally satisfies AC "no hallucinated item IDs" |
| BL-079 | Active | SS-020: cross-user combination-signature cache key |
| BL-080 | Active | Epic 6: global trend clusters, not per-user nightly Claude calls |
| BL-081 | Active | Cloudflare Turnstile + WAF on OTP endpoint before launch (SMS-pumping) |
| BL-082 | Active | Budget-based (paise) rate limiting to supersede call-count limits — extends `BL-062` |
| BL-083 | Parked | Upstash → Durable Objects at multi-instance deploy (links `BL-037`) |
| BL-084 | Parked | pgvector adoption at first similarity-search need |
| BL-085 | Parked | PostHog event-sampling policy before 1M events/month |
| BL-086 | Parked | Sentry-backend → PostHog error tracking at paid-tier crossover |
| BL-087 | Parked | Re-verify Replicate per-action pricing — currently an unverified inherited assumption underpinning the entire COGS model |

`BL-087` deserves emphasis: **the ₹4.15 try-on figure drives ~40–50% of projected AI COGS and has never been checked.** It is the least-verified, highest-leverage number in the business model.
