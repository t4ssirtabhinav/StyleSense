# StyleSense — Architecture Amendments

`init documents/architecture-hld-lld.html` is the original HLD/LLD and is never edited in place — it stays the fixed Phase-1 source-of-record. This file is what gets edited instead: a dated, append-only log of every place reality has diverged from that original document, so "why does the code have X and the architecture doc doesn't mention it" always has a traceable answer.

**Logging:** any ticket created via `.claude/skills/new-feature/SKILL.md` (New-Scope Intake Mode) that changes or extends something the original architecture doc didn't cover gets one entry here, added during Stage 2 finalize. Entries are also fair game for the `/audit` skill's architecture-drift check to add, if it finds code that no longer matches the original doc and no amendment already explains why.

**Format** — one entry per amendment, oldest first, never edited after being written (if a later amendment supersedes an earlier one, say so in the new entry rather than rewriting the old one):

```
## AMEND-001 — <short title> (YYYY-MM-DD)

**What changed:** <what's true now that isn't in architecture-hld-lld.html>
**Introduced by:** <SS-XXX>
**Why the original doc didn't cover it:** <one line — genuinely new idea, scope grew, a wrong assumption at Phase 1, etc.>
**Original doc section this touches:** <e.g. "Database Schema", "AI Architecture" — so a reader knows what's now stale>
```

---

## AMEND-001 — Occasions become a data registry, not a Postgres ENUM (2026-07-28)

**What changed:** `occasion_type` — the 12-value `CREATE TYPE … AS ENUM` in `001_initial.sql` — is replaced by an `occasions` registry table (plus `occasion_aliases`), with `wardrobe_items.occasion_tags`, `outfits.occasion`, `suggestion_sessions.occasion` and `social_posts.occasion` storing `TEXT`/`TEXT[]` slugs. Occasions now carry metadata the enum could not express: hierarchy (`parent_key`), regional and cultural scope, formality, per-occasion styling rules, date rules, tier gating and badge colour. Adding an occasion becomes an `INSERT` — no migration, no type regeneration, no mobile release.

**Introduced by:** SS-025 (foundation for SS-020, SS-030, SS-031)

**Why the original doc didn't cover it:** the Phase-1 assumption was that a fixed set of occasions was sufficient for the MVP. That holds for a wedding-and-office product; it does not hold for the actual India surface area — regional festivals (Ganesh Chaturthi, Navratri, Onam, Pongal, Durga Puja, Bihu), year-round regional weddings, travel and international travel, sports and fitness, and milestone events (Griha Pravesh, Godh Bharai). A Postgres enum cannot have values removed or reordered, cannot carry metadata, and has no hierarchy — so a calendar-driven, regional occasion feature is not buildable on it. This was a wrong assumption at Phase 1, not scope growth.

**Original doc section this touches:** Database Schema (the `occasion_type` enum and all four columns using it); also downstream — Style Score's "8 occasions" coverage metric and the tagging vocabulary in the AI Architecture section.

---

## AMEND-002 — Styling AI becomes multi-provider, config-routed, with a deterministic pre-filter (2026-07-28)

**What changed:** the original design called for a Claude Sonnet call over a serialised full wardrobe. Reality now: (1) a deterministic pre-filter (SS-027) generates and scores candidate outfits with no LLM and no network, and the model's job narrows to ranking ~5 candidates and writing reasoning; (2) a router (SS-028) selects provider *and* model per request from an `app_config` table (SS-026) using task complexity, provider quota/health, and user tier — Gemini and Anthropic both serve styling traffic behind the unchanged `IStylingProvider` port; (3) rate limiting moves from call-count to **budget (paise)** with a per-request cost ledger (SS-029); (4) the suggestion cache keys on a cross-user combination signature rather than `user_id`.

**Introduced by:** SS-026, SS-027, SS-028, SS-029 — assembled by SS-020

**Why the original doc didn't cover it:** Phase 1 treated model choice as a fixed implementation detail and cost as an operational afterthought. At verified 2026-07-28 pricing the original design costs ₹1.89/call versus ₹0.024–0.125/call for the revised one, and the Epic 6 trending-picks spec (nightly per-user Claude call) would have cost ~₹463 Cr/year at Year-5 scale. Cost is a first-class architectural constraint at Indian consumer scale, not a tuning exercise. Multi-provider routing additionally serves capacity (separate quota pools) and availability (SS-020's "never a hard error" AC is satisfied by failing over to a second vendor rather than degrading). Analysis: `docs/proposals/EXECUTION-PLAN.md` and `docs/proposals/PLATFORM-CONSOLIDATION*.md`.

**Original doc section this touches:** AI Architecture (provider assignment per task); API Endpoints (`POST /ai/outfit-suggest`); the MVP infrastructure-cost estimate in the Cost section, which assumed ~₹200–800/month and did not model per-call AI cost at scale.

---

## AMEND-003 — Garment types become a data registry with structural slots (2026-07-30)

**What changed:** `wardrobe_category` — the 21-value `CREATE TYPE … AS ENUM` at `001_initial.sql:7-14` — is replaced by a `garment_types` registry (plus aliases and unknown-capture), carrying what an enum cannot: a `parent_key` hierarchy, a **closed structural `slot`/`layer` set that code may switch on**, multi-valued cultural `register`, `requires_with`/`pairs_with`/`excludes_with` edges, coverage, region/culture scope, and per-type styling rules. Adding a garment type becomes an `INSERT`. This is the **second** enum retired by the same expand→migrate→contract playbook AMEND-001 established. The accompanying principle: **taxonomies and cultural vocabulary are data; only physically-closed structural roles stay in code.** Garment *behaviour* is scored from attributes rather than from type identity, so a newly-inserted type is stylable with no engine change.

**Introduced by:** SS-034 (EXPAND phase; MIGRATE/CONTRACT and the item-attribute registries follow in Wave 2), with SS-036 applying the same registry shape to `pattern`/`fabric`

**Why the original doc didn't cover it:** Phase 1's 21 categories are a western-shaped vocabulary containing **zero ethnic bottoms** — no churidar, salwar, patiala, palazzo, dhoti, pyjama or sharara — and no way to express silhouette, region, culture, layering or garment-to-garment compatibility. That is why the styling engine can only offer *kurta with jeans*, and no scoring change fixes a vocabulary that cannot express the outfit. A wrong assumption at Phase 1, not scope growth. Sourced taxonomy (web-researched, with citations): `docs/proposals/STYLING-ENGINE-V2.md` Appendix B, which also records five modeling problems the research exposed — notably that a "kurta set" is a *set* rather than a garment, and that several regional garments (mekhela sador, mundum neriyathum) are genuinely two-piece.

**Original doc section this touches:** Database Schema (the `wardrobe_category` enum and `wardrobe_items.category`); AI Architecture (the tagging vocabulary, which needs two-stage coarse→fine prediction once label count grows); indirectly the Footwear module, which becomes a `slot` rather than a module.

---

## AMEND-004 — Suggestion quality becomes measured rather than asserted (2026-07-30)

**What changed:** suggestion requests, the candidates actually shown, and the user's reaction are recorded as first-party rows (the existing `suggestion_sessions` extended, plus new `suggestion_impressions` and `suggestion_outcomes`), and wear history gains occasion-awareness (`occasion_key`, `outfit_id`). Together these make the styling engine **stateful with respect to its own history** — enabling anti-repetition across sessions, occasion-scoped novelty ("worn to office Tuesday, fresh for a festival"), and a tunable effort dial whose effect can actually be measured. Crucially this does **not** abandon determinism: recent-wear and recently-shown become explicit *inputs*, so same-input-same-output still holds while the output rotates naturally. **Extends AMEND-002 rather than superseding it** — the deterministic pre-filter, the config-routed provider ladder, and the combination-signature cache all remain true.

**Introduced by:** SS-033 (impression/outcome substrate), SS-035 (occasion-aware wear history) — wired at the call sites by SS-020 and SS-023

**Why the original doc didn't cover it:** Phase 1 modelled suggestion as a stateless request/response with no concept of a feedback loop, and treated suggestion *quality* as a property of the prompt rather than something observable. Two consequences make the omission non-neutral: impression data **cannot be backfilled**, so every day without it is permanently lost personalization data; and a tuning dial with no outcome metric is theatre. Reasoning: `docs/proposals/STYLING-ENGINE-V2.md` §5–§7.

**Original doc section this touches:** Database Schema (`suggestion_sessions`, `wardrobe_item_wears`); AI Architecture (suggestion as stateless request/response); the Analytics section, which specified client-side funnel events only and has no notion of a first-party training substrate.

---

## AMEND-005 — Authentication becomes multi-provider; passwords are now stored (2026-08-15)

**What changed:** authentication is no longer single-method. Phone OTP remains the **default and primary** method — nothing about the India-first reasoning is retracted — but email/password is added as an alternate, which means password storage (Supabase-managed) now exists, directly contradicting the original doc's explicit "No password storage needed." Google OAuth was scoped in the same intake and **deferred** — it is not shipping in this amendment's tickets and holds no reserved ticket ID. Three structural consequences accompany the change: (1) the login screen becomes a *method host* rather than a phone form, so a further method is an addition rather than a rewrite; (2) post-authentication onboarding routing is hoisted out of the phone-OTP screen into one shared mechanism that runs for any session however it was minted — fixing a pre-existing bug where a returning user with incomplete onboarding was never re-prompted (`BL-168`); (3) sign-out exists for the first time (`BL-167`), which makes clearing all user-scoped client state a security concern rather than a nicety. An **account-linking policy is established now, ahead of the feature**: linking is always user-initiated while already authenticated (mirroring Supabase's own `linkIdentity()` shape), never automatic on a matching value alone, and an identifier already owned by a different account is blocked with a clear message rather than auto-merged (`BL-172`, `[VERIFIED 2026-08-14 via WebSearch]`). No linking UI is built; the schema and trigger changes are constrained so as not to preclude one.

**Introduced by:** SS-071 (auth foundation: method host, sign-out, routing hoist), SS-072 (email/password + migration `021`) — with SS-070 (test-user seed script) as sibling tooling from the same intake

**Why the original doc didn't cover it:** Phase 1 correctly identified phone-first as the right India default, and that judgment stands. What it did not anticipate is that phone OTP delivery is gated behind TRAI DLT registration (`BL-001`, re-verified 2026-08-14: MSG91 still needs a custom Send-SMS-Hook Edge Function, and DLT applies to the destination number regardless of sending vendor) — so the primary method cannot deliver a single real SMS during beta. The alternate method exists to route around an external-provisioning blocker, not because phone-first was wrong.

**Original doc section this touches:** Security Architecture ("Phone OTP Primary" / "No password storage needed"); indirectly Database Schema — `public.users.email UNIQUE` combined with `002`'s auto-provisioning trigger guarding only `ON CONFLICT (id)` means a duplicate email aborts the auth signup transaction with an opaque `500` (`BL-169`), which migration `021` hardens; and `public.users.phone` staying nullable is what makes a phone-less identity representable at all.
