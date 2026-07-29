# Business & Investor Case — Platform Consolidation and Model Resizing

**Status:** Analysis. Not a fundraising document — an input to one.
**Companion to:** [`PLATFORM-CONSOLIDATION.md`](PLATFORM-CONSOLIDATION.md) · [`PLATFORM-CONSOLIDATION-TECHNICAL.md`](PLATFORM-CONSOLIDATION-TECHNICAL.md)
**Resizes:** the *StyleSense — Business Plan & Investor Memo* artifact (FY2026)
**Date:** 2026-07-28

> **Provenance:** AI and platform pricing verified 2026-07-28 (see the proposal doc's provenance table). **Replicate pricing, all revenue assumptions, conversion rates, ARPU, CAC, and market sizing are unverified** — carried from the existing memo or estimated here. Every projection below is a planning estimate, not a forecast.

---

## 1. The one slide that matters

The existing memo asks investors to believe a ₹152 Cr Year-5 business with 45% EBITDA margins. Having now pulled real vendor pricing and traced it against the actual product spec in `init documents/epics-tickets.html`, here is what I found:

**The trending-picks feature, exactly as specified, costs ₹463 Cr per year at Year-5 scale — 5.4× the entire company's revenue.**

The spec says: nightly cron, 2am IST, five personalised picks per user, via Claude. At 6.8M average MAU that is 204M AI calls per month. At Claude Sonnet 5 over a full wardrobe context (₹1.89/call `[VERIFIED pricing, ESTIMATED tokens]`), that is **₹38.6 Cr/month — ₹463 Cr/year — against ₹85 Cr of annual revenue.**

Switching to the cheapest credible model doesn't save it: Gemini 2.5 Flash brings it to ₹56 Cr/year, still **66% of all revenue for one feature**. **Only the architecture saves it.** Computing trend clusters once globally and matching them to wardrobes locally costs **₹1,770/month — ₹21,000/year — flat, at any user count.**

₹463 Cr/year → ₹21,000/year. Same feature, same output to the user, one design decision.

**That is the entire thesis of this document: at consumer scale in India, architecture *is* the business model.** Not vendor negotiation, not headcount, not even pricing. Three design decisions — global-not-per-user, pre-filter-then-rank, cross-user caching — compound to roughly **12×** on unit cost and survive every future vendor change, price rise and model deprecation. Vendor selection is the last 2–8× on top, and it is the only part someone can take away from us.

None of it has been built yet. All of it is cheap to build correctly the first time.

---

## 2. Honest resizing of the memo

I've applied five corrections. Each is defensible; together they cut Year-5 revenue by ~44% and *raise* costs — and the business still works, which is the point worth making to an investor.

### Correction 1 — The affiliate line is a bet, not a base case

This is the load-bearing beam. The memo's Y5 affiliate revenue of ₹75.4 Cr assumes **9–11% of MAU purchase monthly** through the app at ₹1,300 AOV and **6% commission**.

| Assumption | Memo | Realistic | Source of the gap |
|---|---|---|---|
| Monthly purchase rate | 9–11% of MAU | **1–3%** | Content-to-commerce norms |
| Commission | 6% | **3–5%** | Indian fashion affiliate rates; often 0% on sale items and new-customer-only |
| Attribution capture | implicit 100% | **~75%** | App-to-app deep links routinely break web-cookie attribution |
| **Y5 affiliate revenue** | **₹75.4 Cr** | **~₹9 Cr** | |

**This single correction removes ₹66 Cr from a ₹152 Cr plan** — and with it, the memo's central claim that *"a free user tapping one affiliate link a month generates ₹78, so the free base is an asset, not a cost centre."*

Run the free-user unit economics honestly:

| | Memo's implied case | Realistic case |
|---|---|---|
| Free-user revenue/month | ~₹7 (affiliate) + ₹1.5 (ads) | ~₹1.44 (affiliate) + ₹1.5 (ads) |
| Free-user lifetime (~8 mo) | ~₹68 | **~₹24** |
| Free-user COGS (₹35–50 onboarding spike + ~₹3/mo) | ~₹60 | ~₹60 |
| **Net** | **≈ break-even** | **≈ −₹36** |

**Free users are not revenue-positive.** They are an acquisition-and-data cost, justified by conversion and the wardrobe graph — which is a completely normal, fundable consumer story. But it is a *different* story than the memo tells, and an investor who models it will find this in twenty minutes.

**The strategic reframe:** stop claiming free users pay for themselves. Claim instead that *free-user COGS is a controlled, engineered variable* — ₹60 today, ₹25 after the architectural fixes — and that this is a capability, not an accident. That is a stronger position, because it is true and it is demonstrable.

### Correction 2 — Net ARPU

₹149 − 18% GST = ₹126 − 15% Play billing = **₹107**. The memo's ₹110–130 range: the floor is right, the ceiling isn't reachable. Subscription line ×0.86.

*(Also: the memo says ₹799/yr; the epics and implementation docs both say ₹999/yr. Pick one before anyone external reads both.)*

### Correction 3 — Infrastructure was understated, and the gap is a *scenario* problem

The memo budgets **₹1.40/MAU/month** at Y5. Bottom-up, with the consolidation and architectural fixes fully implemented: **~₹2.95/MAU/month**. Without them — per-user nightly Claude calls, Sonnet over full wardrobe contexts, and try-on at the uptake the go-to-market section actually requires — it is **~₹65/MAU/month**, dominated by the trending-picks line in §1.

| Scenario | Y5 infra + AI | vs resized revenue (₹85 Cr) |
|---|---|---|
| Memo's assumption | ₹11.4 Cr | 13% |
| **With all fixes** | **₹24.1 Cr** | **28%** |
| Without fixes | ~₹530 Cr | **623% — insolvent several times over** |

The memo is not merely optimistic here; it describes a scenario in which **the viral loop never fires**. §07 makes free try-on the acquisition engine; §06 prices try-on at ₹4.15 and budgets ₹1.40/MAU total. Those cannot both be true. If growth works, COGS breaks; if COGS holds, growth missed.

**This is the objection I would lead with as an investor, and it is absent from the memo's own objection table.**

### Correction 4 — Year-1 UA math

₹1.2 Cr at ₹40–60 CAC = 200k–300k installs. The memo claims 150k EOY MAU — a 50–75% install→retained-MAU rate against consumer benchmarks of 10–25% at D30. Realistically that budget buys **40–70k MAU**. Year-1 is roughly 2–3× optimistic on the growth curve.

### Correction 5 — Missing cost lines

SMS/OTP (and **SMS-pumping fraud**, which the app currently has no protection against), content moderation for the OOTD feed (named as a headwind, budgeted at zero), customer support, and GST on the revenue side.

---

## 3. The resized model

Two structural additions offset part of the haircut — the high-end monetisation layer described in §4.

### Year 5 (6.8M avg MAU) — ₹ Crore

| Line | Memo | Resized | Note |
|---|---|---|---|
| Subscription (₹149 tier) | 42.43 | **36.5** | net ARPU ₹107 |
| **High-end layer** (Atelier + Wedding Pass) | — | **19.0** | new; §4 |
| Affiliate commerce | 75.40 | **9.0** | 3% conv, 4% comm, 75% attribution |
| Ads | 17.23 | **12.0** | 30% haircut |
| Brand · B2B · credits | 17.16 | **8.6** | 50% haircut (speculative lines) |
| **Total revenue** | **152.22** | **85.1** | **−44%** |
| Infrastructure & AI | (11.42) | **(24.1)** | with all fixes |
| Team | (26.00) | (26.00) | |
| Marketing / UA | (40.00) | (40.00) | |
| G&A | (7.00) | (8.5) | + moderation, support |
| **EBITDA** | **67.80** | **(13.5)** | |

### Year 3 (1.3M avg MAU) — the Series A gate

| Line | Memo | Resized |
|---|---|---|
| Subscription | 5.62 | 4.8 |
| **High-end layer** | — | **3.6** |
| Affiliate | 10.95 | 1.6 |
| Ads | 2.42 | 1.7 |
| Brand · B2B · credits | 2.52 | 1.3 |
| **Total** | **21.51** | **13.1** |
| Infra & AI (with fixes) | (4.06) | (4.6) |

**What the resized model says:** at conservative assumptions the business does **not** reach ₹152 Cr or 45% EBITDA by Year 5. It reaches roughly **₹85 Cr and around break-even** — a real, venture-scale company on a slower curve, needing either one more funding round or a slower UA ramp.

**Do not present this as failure.** Present it as the floor. The memo's numbers are the *upside* case, gated on one testable variable — affiliate conversion. Showing both, and naming the variable that moves between them, is a materially stronger investor position than a single optimistic column. Sophisticated investors discount aggressive projections automatically; they cannot discount a founder who has already done it for them and named the test.

**The Seed's actual job, restated:** not "reach 700k MAU," but **prove affiliate conversion and free-user COGS**. Those two numbers decide whether the Series A story is the ₹85 Cr version or the ₹152 Cr version. Everything else is execution.

---

## 4. The high-end layer — where the resizing recovers

The high-end monetisation layer contributes **₹3.6 Cr at Y3 (28% of resized revenue)** and **₹19 Cr at Y5**. It is the single largest recovery in the resized model, and it is the one revenue line that **raises ARPU without raising CAC** — it monetises users already acquired.

### Two instruments, not one tier

**Wedding Season Pass — ₹2,999 for 90 days.** Indian luxury fashion spend is spiky, not recurring; it is weddings. A user anchors ₹2,999 against a ₹5–15L wedding budget, not against Netflix. ~10–12M Indian weddings a year; we need a rounding error of them. Sold as an **in-app consumable fired at the moment a user taps the `wedding_guest` occasion** — near-zero incremental CAC, no paywall restructuring, and it tests high-end willingness-to-pay with real money instead of a survey.

**"Atelier" — ₹499/month.** Unlimited try-on, cost-per-wear analytics, wedding-series planning, priority (non-batched) generation. At **0.3–0.6% of MAU** — the credible band for a ₹499 consumer subscription in India — this adds 50–80% to the subscription line.

### Why this segment, and why us

The target is not "rich people." It is people whose **cost per wear is high enough that the number is interesting**: brides and wedding parties (₹50k–₹5L outfits), designer-wardrobe buyers, **fashion creators** (wardrobe is a deductible business asset — an entirely different willingness-to-pay curve), and **NRIs** (₹999 ≈ $12).

**The hook is already shipped.** SS-015 landed `cost_per_wear` as a generated column, backed by a real wear-history log. For this segment that is not a feature, it is *the* pitch:

> *"Your ₹80,000 lehenga is sitting at ₹80,000 per wear. Here are four ways to restyle it."*

Nobody in India is saying that to a luxury buyer. Myntra can't — telling you to re-wear what you own cannibalises their business. That single sentence justifies ₹499–999 far better than "unlimited suggestions" ever will.

### Recommendation: do not ship three tiers at launch

Three tiers pre-PMF fragments the paywall, complicates the pricing screen, and dilutes ₹149 conversion — the only metric a Seed investor will diligence.

1. **Launch:** Free + ₹149. Clean.
2. **Simultaneously:** Wedding Pass as a **consumable**, not a tier. Zero paywall complexity, real high-end price discovery.
3. **Month 6+, on data:** introduce ₹499 Atelier, built from what the top decile of usage actually consumed.

**For the investor conversation:** a third tier in a pre-launch deck reads as revenue-modelling optimism. A third tier with 4,000 paying users reads as **pricing power** — and pricing power is the single most persuasive answer to the "Indian ARPU is too low" objection, which is the first objection any India consumer deck receives.

---

## 5. The moat — separating real from asserted

| Claimed moat | Verdict |
|---|---|
| Ethnic + occasion intelligence | **Real, but shallow-fast.** A funded competitor replicates the taxonomy in ~6 months. It's a head start, not a moat |
| Hexagonal AI architecture | **Real, and now demonstrable.** See below |
| First-mover / no India-native competitor | **Timing, not a moat.** Timing expires |
| The wardrobe graph | **The real one.** See below |
| Cross-platform neutrality | **Real and structural.** Myntra cannot credibly recommend Ajio. We can |

### The one genuinely un-copyable asset: wear data, not purchase data

**Myntra knows what Indians buy. We will know what Indians actually wear.**

SS-015 shipped a wear-history log and cost-per-wear. Every entry is a proprietary signal that no e-commerce platform can obtain, because the wearing happens outside their surface entirely. That asymmetry compounds: wear data → better suggestions → retention → more wear data. It cannot be bought, scraped, or bootstrapped with capital — only accumulated with time and users.

**It also has a second life as a product moat**: "what actually gets worn" is the ground truth for the styling model, for gap analysis, for trend prediction, and eventually for training an India-fashion model. This is what justifies a strategic premium at exit, and it is the thing to instrument hardest from day one.

### The architecture moat is now provable, not asserted

The memo claims: *"AI providers sit behind ports… swappable to cheaper models tomorrow. This is what lets gross margin expand as we scale."*

Until now that was an assertion. The consolidation work makes it a **demonstration**: a second `IStylingProvider` implementation running the same feature at **8× lower unit cost**, switchable by configuration, with the port unchanged.

That converts a slide into a diligence artifact. **"We reduced the unit cost of our core feature 8× without changing a line of business logic"** is a materially different claim than "our architecture is flexible" — and it directly answers the strongest technical objection in the memo's own table (*"Avatar/AI cost blows up at scale"*).

---

## 6. Leverage — ranked by return per unit of effort

| # | Leverage | Return | Cost |
|---|---|---|---|
| 1 | **Architectural** — global clustering, pre-filter, cross-user cache | **~12× unit cost**, permanent, vendor-independent | **~17h marginal** |
| 2 | **Provider routing** — Gemini volume tier / Claude quality tier | further 2–8× on text AI | ~27h diligence + config |
| 3 | **Segment** — Wedding Pass + Atelier | +28% revenue at Y3, **no CAC increase** | product work, no infra |
| 4 | **Data** — wear-log flywheel | compounding, un-copyable | already shipped |
| 5 | **Distribution** — creators, wedding/festival seasonality | CAC below paid benchmarks | ongoing |
| 6 | **Time** — the AI cost curve falls | passive margin expansion | free, *if* #1 and #2 exist to exploit it |

**Leverage #1 costs ~17 hours and returns more than every other line combined.** It is available exactly once — before SS-020 and Epic 6 are written. Both are unwritten today.

**Leverage #6 is worth dwelling on for the investor conversation.** Model prices fall and capability rises on a steep curve; today's ₹0.23 call is plausibly ₹0.05 in two years. But that only reaches the P&L if model choice is configuration rather than code. The ports architecture is what turns an industry trend into *our* margin expansion. Without it, we watch the curve fall and pay old prices.

---

## 7. Strategy: what actually changes

**Stop claiming free users are self-funding.** Claim that free-user COGS is engineered and falling. Show ₹60 → ₹25. That is a defensible, evidenced statement; the current one is a bet on affiliate assumptions being 3× industry norms.

**Make affiliate conversion the #1 pre-Series-A experiment.** It is the difference between ₹85 Cr and ₹152 Cr at Y5. It is testable with a few thousand users and a handful of deep links. Nothing else in the model has that ratio of decision-value to test-cost. **Test it in month 2, not month 12.**

**Price the ₹149 tier to cover COGS; let commerce and the high-end layer carry margin.** But that only works if "unlimited" becomes **"unlimited fair use"** with a real, invisible-to-97% ceiling. An engaged premium user currently costs more than ₹107 net.

**Reclassify share-producing try-on cost from COGS to UA.** If a generation ends in an Instagram/WhatsApp share, that ₹4.15 is acquisition spend. It is honest accounting and it fixes the gross-margin optics that the current framing damages.

**Add the missing objection to the deck's §10 table**, with its answer:

> **Objection:** *"Your viral loop and your largest COGS line are the same action. You can't rate-limit try-on without killing growth, or free it without killing margin."*
>
> **Counter:** Try-on is permanently cached per combination, generated on share-intent rather than on view, uses 2D compositing for previews with generative reserved for share cards, and moves to dedicated inference (5–20× cheaper than per-call serverless) at Series-A scale. Share-producing generations are attributed to UA, not COGS, because that is what they are.

That objection is currently the deck's sharpest unaddressed vulnerability. Answering it pre-emptively converts it into evidence of unusual unit-economics rigour.

**Verify ₹4.15 before any external financial claim.** It drives ~40–50% of AI COGS, it has never been checked, and it is a two-hour task. Being wrong about it in a room full of investors is unrecoverable in a way that being conservative never is.

---

## 8. What to say to whom

**To an investor:** *"We rebuilt our cost model from verified vendor pricing and found our own trending-picks spec would have cost ₹463 Cr a year at scale — 5× our revenue. We redesigned it to ₹21,000 a year before writing a line of it. Here's the conservative model and the upside model, and here's the single variable — affiliate conversion — that moves between them. We're testing it in month 2."*

That is a founder who has stress-tested their own plan. It is worth more than a better-looking projection.

**To a business owner:** the ₹149 tier will not carry this business at Indian ARPU. Commerce and the high-end layer carry it. The subscription's job is to cover COGS and to signal that the product is worth paying for.

**To an engineer:** the three architectural decisions in the technical doc are worth more than every vendor negotiation available for the next three years — and they expire the moment SS-020 and Epic 6 are written.

**To yourself:** the memo's strategy is sound. The affiliate thesis, the cultural moat, the freemium design, the ports architecture — all correct. What needs work is the arithmetic and one unexamined contradiction between the growth plan and the cost plan. That is a far better position than the reverse.

---

## 9. Decisions required

| # | Decision | Deadline |
|---|---|---|
| 1 | Approve Tier A architectural changes to SS-020 and Epic 6 | **Before SS-020's Architect phase** — the window closes when the code is written |
| 2 | Fund the ~27h AI provider eval (TD-01…TD-06) | Same |
| 3 | Adopt the resized model as the base case, memo's as upside | Before any external conversation |
| 4 | Approve Wedding Pass as a launch consumable | Sprint 5 planning |
| 5 | Defer the ₹499 Atelier tier to month 6+, data-driven | — |
| 6 | Verify Replicate pricing (2h) | Before any external financial claim |
| 7 | Test affiliate conversion with real deep links | Month 2 of launch, not later |
