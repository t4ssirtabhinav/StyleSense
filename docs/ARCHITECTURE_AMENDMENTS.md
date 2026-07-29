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
